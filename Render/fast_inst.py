import pickle
import matplotlib.pyplot as plt
import pandas as pd
import io
import logging
import time
import base64


from PIL import Image
from io import BytesIO
from typing import Dict, List, Optional, Tuple
from fastapi import FastAPI, Form, Response
from fastapi.responses import HTMLResponse, StreamingResponse


from apicall_input import main_api_call 
from data_extraction_v2 import main_extract_transform
from training_insights.store import create_session_context
from training_insights.summaries import build_activity_summaries

logger = logging.getLogger(__name__)

logger.setLevel(logging.DEBUG)

# Create and configure handlers
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO) # Only show INFO, WARNING, ERROR, and CRITICAL messages in the console

file_handler = logging.FileHandler("app_errors.log")
file_handler.setLevel(logging.ERROR) # Only write ERROR and CRITICAL messages to the file

formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s")
formatter.converter = time.gmtime
# Set the formatter for both handlers
console_handler.setFormatter(formatter)
file_handler.setFormatter(formatter)
# Add handlers to the logger
logger.addHandler(console_handler)
logger.addHandler(file_handler)

def normalize_user(row: pd.Series, mean_df: pd.Series, std_df: pd.Series) -> pd.Series:
    z = (row - mean_df) / std_df
    return z

def getMeanStd_user(data: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
    # drop the date column while the normalisaition is going on
    data_no_date = data.drop(columns =['Date'], errors = 'ignore')
    mean = data_no_date.mean()
    std = data_no_date.std()
    std = std.replace(0.0, 0.01)
    return mean, std

def norm_user_data(df: pd.DataFrame) -> pd.DataFrame:
    # Get the mean + std dev
    user_means, user_std = getMeanStd_user(df.copy())
    user_normalized = df.apply(lambda x: normalize_user(x, user_means,user_std), axis=1)
    user_normalized = user_normalized.drop(columns=[ 'Date'], errors='ignore')
    return user_normalized

def runitall(email: str, password: str, zone3: int , zone5: int ) -> Tuple[BytesIO, str]:
    """ 
    run all functions to get the image
            email: str : user email for api call
            password: str : user password for api call
        return: buffer_img : image buffer with the plot
    """
    # Sanity Check
    if zone5 <= zone3:
        raise ValueError("Zone 5 is by definition a higher hr than zone 3, try again,"
        " and if you aren't sure of your own heart rate zones,try z3 = 150 and z5 = 180 as an estimate")
    
    # import model
    try: 
        with open('mvp2best_logistic_model.pkl', 'rb') as file:
            model = pickle.load(file)
    except FileNotFoundError:
        logger.error("Model file not found. Please ensure 'mvp2best_logistic_model.pkl' is in the project directory.")
        raise
    except Exception as e:
        logger.error(f"An error occurred while loading the model: {e}")
        raise
    logger.info("Model loaded successfully.")

    #pipeline steps
    try:    
        start_date, end_date, runs, other, activity_records = main_api_call(
            email,
            password,
            Z3_min=zone3,
            Z5_min=zone5,
            include_activity_records=True,
        )
    except Exception as e:
        logger.error(f"An error occurred during the API call: make sure email and password are correct, and try again")
        raise
    logger.info("API call completed successfully.")
    try: 
        df = main_extract_transform(start_date, end_date, runs, other, zone3, zone5)
    except Exception as e:
        logger.error(f"An error occurred during data extraction and transformation: {e}")
        raise
    logger.info("Data extraction and transformation completed successfully.")

    # add the normalisation step
    try:
        norm_df= norm_user_data(df)
    except Exception as e:
        logger.error(f"An error occurred during data normalization: {e}")
        raise
    logger.info("Data normalization completed successfully.")

    # make predictions
    try:
        df['injury probabilities'] = model.predict_proba(norm_df)[:, 1]
    except Exception as e:
        logger.error(f"An error occurred while making predictions on converted data: {e}")
        raise
    logger.info("Predictions made successfully.")

    try:
        activity_summaries = build_activity_summaries(activity_records, df, recent_days=90)
        session_id = create_session_context(
            start_date=str(start_date),
            end_date=str(end_date),
            zone3=zone3,
            zone5=zone5,
            activity_records=activity_records,
            activity_summaries=activity_summaries,
        )
        logger.info("Training insights context prepared with %s summaries.", len(activity_summaries))
    except Exception as e:
        logger.error(f"An error occurred while creating training insights summaries: {e}")
        raise

    # plot the probabilities over time with a rolling mean
    plt.figure(figsize=(10,5))
    plt.title('Injury Risk score over time')
    plt.xlabel('Date')
    plt.ylabel('Injury Risk Score (0-1)')
    # add faint horizontal lines at 0.2, 0.4, 0.6, 0.8
    plt.axhline(y=0.2, color='r', linestyle='--', alpha=0.3)
    plt.axhline(y=0.4, color='r', linestyle='--', alpha=0.3)
    plt.axhline(y=0.6, color='r', linestyle='--', alpha=0.3)
    plt.axhline(y=0.8, color='r', linestyle='--', alpha=0.3)    

    plt.plot(df['Date'],df['injury probabilities'])#.rolling(window=3).mean())
    plt.xticks(df['Date'][::5], rotation=45, ha='right')
    plt.ylim(0, 1)
    plt.tight_layout()
    # Save to buffer
    buffer_img = io.BytesIO()
    plt.savefig(buffer_img, format="png")
    buffer_img.seek(0)
    plt.close()

    return buffer_img, session_id

app = FastAPI(
    title = 'Run Injury Prediction API',
    description = 'Predicting injury risk based on GarminConnect running data'
)

# Endpoint to handle form submission and show 'loading'
@app.get("/", response_class=HTMLResponse)
async def login_form():
    html_content = """
    <html>
        <head><title>Injury Risk Prediction</title></head>
        <body>
            <h2>Login with Your Garmin Credentials to Generate Injury Risk Prediction</h2>
            <p style="max-width:600px; font-size:14px; color:#333;">
                So the goal of this tool is to improve on the common recommendation - 
                "Increase mileage by maximum 10% per week" and serve as a guide for you to self 
                manage your own training load.<br/><br/>
                I've trained a model that does this by taking into account both your acute 
                training history over the past week, as well as your 'form' over the past three weeks. <br/>
                The model looks at not only your total training volume over those time periods but also the intensity 
                of that training, with heart rate zones as a proxy for intensity.<br/><br/>
                <b> Note that the model assumes that you have not been injured during 
                the three weeks before any given predicted point(1/day)</b> <br/><br/>
                The method you use to determine your hr zones will have a significant impact on the
                results you get from this tool. Try to pick one that seems the most accurate
                 based on your own percieved effort at that hr. <br/><br/>
                This tool connects to your Garmin training history and uses the machine learning model 
                to produce a visualisation of your injury risk trends for the past few months. <br/><br/>
                Your credentials are only used in memory during processing and are not stored. <br/><br/>
            </p>
            <form action="/predict_and_visualize/" method="post" onsubmit="showLoading()">
                <label> User Email:</label>
                <input type="text" name="email" required><br/>
                <label>GarminConnect Password:</label>
                <input type="password" name="password" required><br/>
                <label>Zone 3 Threshold Heart Rate:</label>
                <input type="range" name="zone3" min="100" max="200" value="150" 
                       oninput="document.getElementById('z3val').innerText = this.value">
                <span id="z3val">150</span><br/><br/>

                <label>Zone 5 Threshold Heart Rate:</label>
                <input type="range" name="zone5" min="100" max="200" value="180" 
                       oninput="document.getElementById('z5val').innerText = this.value">
                <span id="z5val">180</span><br/><br/>
                <button type="submit">Generate Prediction</button>
            </form>
            <p id="loading-message" style="display:none;">Processing... Could take up to 2 minutes, hang in there.</p>
            
            <script>
                function showLoading() {
                    document.getElementById('loading-message').style.display = 'block';
                }
            </script>
            
            
        </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.post("/predict_and_visualize/")
async def predict_and_visualize(email: str = Form(...), password: str = Form(...), zone3: int = Form(...), zone5: int = Form(...)):
    """
    perform spoof calculation and return an image
    """
    logger.info("Received request for injury risk prediction.")
    try:
        # run the full pipeline to get the image
        img, session_id = runitall(email, password, zone3, zone5)
        
           
        # convert to base64 for embedding in <img>
        img_base64 = base64.b64encode(img.getvalue()).decode("utf-8")

        html_content = f"""
        <html>
            <head><title>Injury Risk Results</title></head>
            <body>
                <h2>Your Injury Risk Prediction</h2>
                <p>Below is your personalized risk trend graph. Scroll down for notes on interpretation.</p>
                <p><small>Training insights context prepared for this session.</small></p>

                <img src="data:image/png;base64,{img_base64}" alt="Injury Risk Graph" style="max-width:600px;"/>

                <h3>How to interpret this:</h3>
                <p>
                    I would recommend that you use this tool to examine recent trends in your injury risk score: if 
                    your score has been rising in the most recent segment of the graph, you might want to consider
                    taking a bit of extra rest, or reducing your training load a little. <br/><br/>
                    A score closer to 1.0 indicates higher risk, but from what I've seen so far, 
                    if your score hasn't spent the past week above .6 then you should be in the clear. <br/><br/> 
                    If people start reporting injuries to me, I'll update this with the score they've happened at. <br/><br/>
                    The model was trained on a dataset of competitive runners who trained probably 5-7 
                    days a week who competed at national level in the Netherlands. <br/><br/>
                    I've done some things(normalisation) to have the model make it's predictions based on your own 
                    relative effort, but the way these things work is that the less your training is comparable to the
                    training in the dataset, the less reliable the predictions are likely to be. <br/><br/>
                    The next thing is that this model is very much general purpose:<br/>
                    If you have a history of a specific injury, or a chronic issue, 
                    then this model is not going to be able to take that into account and will under predict your injury risk. <br/>
                    If you have some form issue like a lagging glute med, a big leg length discrepancy, 
                    or an overly aggressive heel strike, then your risk of injury is almost definitely higher than 
                    what the model predicts, so if you aware of something like that, assume your injury risk is higher.<br/><br/>
                    <b> If you have any more questions about how to interpret your results, please 
                    get in touch with me at milomoran123@gmail.com or wherever I messaged you last</b> <br/><br/>
                    Use this as a guide alongside your own judgement and professional advice, it is not a replacement to common sense.
                </p>

                <a href="/">← Back to Home</a>
                <!-- commit2 scaffolding: training insights session id -->
                <div data-training-session-id="{session_id}" style="display:none;"></div>
            </body>
        </html>
        """
        return HTMLResponse(content=html_content)
    
    except Exception as e:
        logger.error(f"An error occurred in the prediction and visualization endpoint: {e}")
        return {"something didn't go quite right with this. Try again to be sure but if no joy send me a quick email at milomoran123@gmail.com and I'll try to figure out what happened": str(e)}, 500
