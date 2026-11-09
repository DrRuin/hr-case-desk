# AI usage notes

I built this with Claude Code. I set the design, read every change, and decided what shipped.

## Where it helped

- Research: three parallel passes over papers (abstention, tau-bench, EU AI Act Articles 12, 14 and 86), my earlier agent projects, and framework docs through MCP servers with current package versions.
- Framework spikes: the same three cases in Pydantic AI, LangChain and Strands with scripted models, so the choice rests on running code and line counts, not on docs.
- Writing the code, the tests and the page, and checking the page in a browser on desktop and phone widths.

## Where I overrode it

- Its first recommendation was LangGraph. After the spikes showed that the important checks were my own code in every framework, I moved the decision out of the model and chose Pydantic AI.
- It proposed reading a confidence value from the model. I replaced that with facts checked in code, because a confident wrong balance is the failure the brief names.
- It proposed Cedar for the approval rule. Cedar can only permit or deny, so a rule that asks a person needed a workaround. Plain decision tables were simpler and also give the explanations.
- Its first explanation picked an input that was sufficient but unhelpful (a leave case escalated "because double booking is unknown" when the service was down). The explanation now starts from the inputs the fired rule names.
- Its first note to the person a case is handed to let the model work out why they were needed and what to do. On live runs the auditor rejected all four notes, because they said things no source held. I had code write those facts as sources instead, and the model now only restates them.

## How I checked its work

- Tests on scripted models for every path, including the failure drill, the approval key and tenant isolation.
- Live runs on the real model after each prompt change, reading every reply and note sentence and the auditor's reason for it. The demo set matches its expected rule 13 of 13, with no rewrites on the last run.
- A review of the handover note by a fresh agent that had not written the code. I applied the findings that held up and wrote down why I left the rest.
