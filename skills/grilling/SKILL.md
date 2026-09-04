---
name: grilling
description: Grill the user relentlessly about a plan, decision, or idea. Use when the user wants to stress-test their thinking, or uses any 'grill' trigger phrases.
---

Interview the user relentlessly until you reach a shared understanding. Map this as a **design tree**: every decision branches into the decisions that hang off it.

Work the tree **one question at a time**. The **frontier** is every decision whose prerequisites are already settled: the questions you can ask _now_ without guessing at answers you haven't heard yet. Pick one frontier question, ask it, and wait for the answer before asking the next — never bundle multiple questions into one turn.

Every question is **multiple choice** with a recommended answer, marked first and labeled "(Recommended)". If a question has only one possible option, don't ask — auto-pick it and tell the user what you picked and why, then move to the next question.

Format a question like so:

```
❓ **Q1** - **<question title>**: <question body, might be multiple paragraphs>

1. <option 1> (Recommended)
2. <option 2>
3. <option 3>
```

Format an auto-picked question like so:

```
🔒 **Q1** - **<question title>**: only one option, <option>. Picked it, no need to ask.
```

Each answer reshapes the tree: a settled decision pushes the frontier outward and unblocks questions that depended on it. Recompute the frontier and ask the next question. A question whose answer depends on another question still open belongs _later_, not now.

Finding _facts_ is your job, never the user's. When a frontier question needs a fact from the environment (filesystem, tools, etc.), dispatch a sub-agent to find it; don't ask the user for anything you could look up yourself. Don't block on it: a running exploration is an unsettled prerequisite, so only the questions downstream of it wait for the sub-agent to report; ask the rest of the frontier now. The _decisions_ are the user's: put each to them and wait.

The session is done when the frontier is empty: every branch of the design tree visited, nothing left silently assumed. Do not act on it until the user confirms you have reached a shared understanding.
