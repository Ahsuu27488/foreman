---
max_turns: 3
allowed_tools: [Skill, Read, Glob, Grep]
tags: [trigger, should-trigger]
---

Rename the getUserData function to fetchUserProfile everywhere in the frontend, there are around 80 call sites across 40 files. Offload it to a cheaper agent and just review what it does.
