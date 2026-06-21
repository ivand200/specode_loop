# Overwrite Only the Owned Skill Directory

Specode Loop will overwrite only `.agents/skills/specode-do-work` in the target project when syncing its bundled workflow skill. It will leave all other `.agents` files and skill directories untouched so target projects can maintain their own repo-level agent configuration alongside Specode Loop's runner-managed skill.
