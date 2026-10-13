# ATLAS Premium R2 beginner human-test protocol

This protocol is for an independent, consented usability session. Automated QA must not be represented as human feedback.

## Participants and setup

- Recruit 5–8 people who invest or are considering investing but do not work on ATLAS.
- Use the exact frozen review SHA and customer-viewer role. Do not expose internal routes or credentials.
- Test desktop at 1440×900 and phones at 390×844 and 360×800.
- Record only consented screen/audio and redact account or portfolio information.

## Tasks

1. On Home, identify the strongest idea and explain in their own words what Action, Opportunity and Confidence mean.
2. Open that exact ticker in Research and identify the price date, Fair Value, principal support and principal risk.
3. Expand **Research 101** and restate why Confidence is not a probability of price appreciation.
4. Interpret the price-versus-SPY chart. Ask what the normalized value 100 means and whether it is a price.
5. Find technical indicators. If unavailable, explain what the page says rather than guessing a value.
6. Add one supported ticker and one missing-price ticker to Watchlist, search, sort, remove and reload.
7. Ask ATLAS why the rating exists and compare its Action, Fair Value, Opportunity and Confidence with Research.
8. Open the incomplete/withheld ticker and identify which facts are unavailable without inferring substitutes.

## Observer rubric

For each task record: completion (yes/no), time, wrong turns, assistance, confidence (1–5), and verbatim misconception. Flag as P1 if a majority misreads certified close as live, Confidence as probability, normalized SPY index as price, or withheld evidence as zero. Flag as P2 for navigation, density or terminology friction that does not change the investment meaning.

## Exit questions

- What would you do next, and which evidence caused that choice?
- Which number was hardest to understand?
- What felt current versus dated?
- Did any unavailable state look like zero or a negative fact?
- Did Ask ATLAS contradict Research?

## Acceptance

- No P0 trust or authorization issue.
- At least 80% unassisted completion for tasks 1–7.
- Zero participants interpret missing evidence as a numeric zero after reading the unavailable state.
- All contradictions are reconciled against the shared `CustomerResearchView` identity before release.

Human execution and findings remain pending until real participants complete this protocol.
