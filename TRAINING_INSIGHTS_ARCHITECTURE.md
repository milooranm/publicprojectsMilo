# Training Insights Architecture Plan

## Status

This document defines the planned architecture for a new Training Insights feature for the Garmin-based injury prediction application.

This commit is planning only. It does not change runtime behavior, APIs, or UI.

## Goal

The Training Insights feature will let a user ask natural-language questions about recent training history while staying grounded in the same Garmin activity data and injury-risk pipeline that already powers the application.

Examples include:

- What was my training like before my fastest 10k?
- When was my highest mileage period?
- Why was my injury risk elevated in May?
- What runs were most similar to this one?

The feature should extend the existing application experience rather than create a separate product.

## Current Baseline

The application already does the following:

- Authenticates with Garmin Connect.
- Downloads recent activity history.
- Aggregates activity data into day-level training features.
- Computes injury-model inputs such as load ratios and ACWR.
- Scores daily injury risk.
- Renders a results page with the injury-risk graph.

The current limitation is that the deployed path keeps the daily aggregates and the final chart, but not enough rich per-activity detail to support question answering over individual runs.

## Design Principles

- Reuse the current Garmin ingestion flow instead of building a parallel pipeline.
- Reuse the current injury feature engineering and prediction outputs.
- Keep version 1 in memory and session-scoped.
- Avoid introducing a database or vector database in version 1.
- Keep the design modular so storage and retrieval backends can be swapped later.
- Keep the feature integrated into the current dashboard and results experience.
- Prefer simple, testable components over heavyweight RAG infrastructure.

## Version 1 Decisions

- Retrieval backend: local lexical embedding approach using scikit-learn and cosine similarity.
- LLM provider: OpenAI for final answer generation.
- Storage model: in-memory session context with expiry.
- Search window: configurable recent history window, with 90 days as the initial default for searchable summaries.
- Deployment model: process-local memory only, with the known tradeoff that state is lost on restart and is not shared across instances.

## Proposed Architecture

The feature will add a Training Insights pipeline on top of the current prediction flow.

The key change is that Garmin ingestion should retain more per-activity information instead of only producing day-level aggregates.

The proposed end-to-end flow is:

1. The user submits the existing prediction form.
2. Garmin activities are fetched and parsed.
3. The ingestion layer returns both:
   - day-level aggregates for the existing injury model
   - per-activity records for the new Training Insights layer
4. The existing injury feature pipeline computes daily load features and injury-related metrics.
5. The existing model scores daily injury probabilities.
6. A summary builder joins each activity record to the final scored data for that activity date.
7. The summary builder creates one searchable summary per activity.
8. A lightweight in-memory retrieval index is built from the summary corpus.
9. The full session context is stored in memory with a time-to-live.
10. The user asks a Training Insights question from the same application experience.
11. The insights service retrieves the most relevant summaries, builds a grounded prompt, calls OpenAI, and returns an answer with supporting evidence.

## Core Data Objects

Version 1 should introduce explicit internal data objects even if the implementation uses simple Python structures at first.

Activity record:

- One object per Garmin activity.
- Keeps per-activity details that are currently discarded too early.
- Includes fields such as activity id, activity type, date, local start time, activity name if available, distance, duration, pace, average heart rate, max heart rate if available, and zone-related distance totals.

Daily risk record:

- One object per scored day.
- Represents the final day-level training and injury context after prediction.
- Includes fields such as date, injury probability, ACWR, 5day to 3 week ratios, total km, session count, weekly aggregates, and alternative training load.

Activity summary:

- One object per searchable summary.
- Contains both structured fields and rendered summary text.
- Structured fields remain available for future hybrid retrieval or similarity logic.
- Summary text is used to build the version 1 retrieval index.

Training session context:

- One object per active user session.
- Holds the full in-memory state needed for insights.
- Includes session id, creation time, expiry time, user-selected heart-rate thresholds, activity records, scored daily data, activity summaries, and the retrieval index.

## Summary Builder Design

The summary builder is a central component of the feature.

It should not run only at ingestion time, because part of the summary depends on the final daily risk outputs that are only available after the injury model has run.

Each summary should have two explicit sections.

Run details:

- Date
- Distance
- Duration
- Pace
- Average heart rate and max heart rate when available
- Zone-related distance information when available
- Simple contextual observations when useful, such as long run, steady run, or higher-intensity session

Risk details:

- Same-day injury probability
- ACWR
- Same-day session count
- Same-day total distance
- Short explanation of why the daily context looked higher or lower risk

Important note:

- The injury features are day-level, not run-level.
- If multiple runs happen on the same day, they will share the same risk-details block.
- The wording should make clear that this is the daily risk context around the run, not a separate model score for that individual run.

The summary builder should keep the numeric fields alongside the text so later versions can support more than pure text-based retrieval.

## Retrieval Strategy

Version 1 retrieval should stay lightweight.

The initial plan is:

- Build search text from the activity summaries.
- Use a local scikit-learn vectorization approach.
- Store the resulting vectors in memory.
- Compute similarity with cosine similarity.
- Return the top-k summaries for a user question.

This choice is intentional:

- It avoids extra infrastructure.
- It avoids extra per-summary API cost.
- It keeps retrieval fast and local.
- It is sufficient for a relatively small personal training-history corpus.

The retrieval layer should still be hidden behind a clean interface so an external embedding provider or vector database can be added later without rewriting the service layer.

## OpenAI Insight Generation

Version 1 will use OpenAI only for the final answer-generation step.

The insight-generation service should:

- Accept a user question and a session id.
- Retrieve the top-k relevant activity summaries from the local index.
- Build a grounded prompt that includes only the retrieved evidence and a small amount of user question context.
- Ask OpenAI for an answer that stays within the evidence provided.
- Return both the answer and the supporting summaries or references used.

The service should be instructed to:

- Prefer evidence over speculation.
- Say when the available evidence is weak or incomplete.
- Refer to specific runs or dates when explaining an answer.
- Avoid claiming facts that are not supported by retrieved context.

## In-Memory Session Storage

Version 1 will keep all Training Insights state in memory for the duration of the user session.

Why this fits version 1:

- It matches the current architecture, which already processes Garmin credentials and data in memory.
- It keeps implementation complexity low.
- It avoids introducing a database before the feature shape is proven.

Mitigations for version 1:

- Add a time-to-live for each session context.
- Replace older context when the same user reruns the prediction flow.
- Cap the number of active contexts.
- Keep stored content limited to the recent summary window and necessary structured fields only.
- Avoid logging sensitive training context or prompts unnecessarily.

## Proposed Module Boundaries

The feature should be added as a small, focused training insights package inside the deployed application area.

The package should be split by responsibility:

- Data models for activity records, daily risk records, summaries, and session context
- Session storage with expiry
- Summary building and enrichment
- Local embeddings and vectorization
- Retrieval and ranking
- Prompt construction
- Training insights orchestration and OpenAI interaction

The existing injury feature module should remain responsible for day-level feature engineering. The existing app entrypoint should remain responsible for HTTP orchestration, but it should stop treating the prediction pipeline as image-only output.

## Integration Points

Garmin ingestion integration point:

- Extend the current Garmin ingestion path so it still returns the daily aggregates needed by the injury model while also retaining richer per-activity records for summaries.

Feature engineering integration point:

- Keep the existing day-level injury feature pipeline focused on engineered training features and risk calculation.
- Do not move RAG logic into the feature engineering layer.

Prediction and session integration point:

- After injury probabilities are computed, create a joined activity-plus-risk view.
- Build activity summaries from that joined view.
- Create the retrieval index.
- Save the resulting session context in memory.
- Return the normal results page together with the information needed for later Training Insights calls.

API integration point:

- Add a new backend endpoint for Training Insights questions.
- Reuse the existing app session flow rather than repeating Garmin ingestion on every question.

UI integration point:

- Add a minimal Training Insights panel to the existing results experience.
- Keep the first version functional and lightweight.

## Commit Plan

Commit 1:

- Architecture and planning document only.

Commit 2:

- Extend activity ingestion to retain per-activity records.
- Add internal data objects and summary-builder scaffolding.
- Produce activity summaries with run details and risk details.

Commit 3:

- Add local embedding and indexing framework using scikit-learn.
- Keep vectors in memory.

Commit 4:

- Add retrieval and ranking logic with tests.

Commit 5:

- Add the Training Insights service and OpenAI prompt orchestration.

Commit 6:

- Add backend API endpoints and session-context handling.

Commit 7:

- Add a minimal Training Insights interface to the existing results page.

## Success Criteria

Version 1 is successful if:

- The current injury-risk workflow still works as before.
- The application keeps enough per-activity detail to answer run-level questions.
- Each searchable summary combines run-specific details with same-day injury context.
- Retrieval works entirely in memory for a single active user session.
- The OpenAI answer is grounded in retrieved summaries rather than free-form speculation.
- The feature feels like an extension of the current dashboard rather than a separate tool.

