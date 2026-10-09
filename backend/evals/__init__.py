"""Quality evals for the AI judgement steps behind the score.

Unit tests mock the model, so they prove parsing, not judgement. These suites
run each judgement step against a labelled dataset and score how often it gets
the answer right. See evals/README.md.
"""
