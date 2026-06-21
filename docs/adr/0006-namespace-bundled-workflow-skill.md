# Namespace the Bundled Workflow Skill

Specode Loop will name its bundled workflow skill `specode-do-work` and copy it into `.agents/skills/specode-do-work` in the target project. The human user does not invoke this skill directly; the namespaced skill name exists so Specode Loop can safely overwrite its own project-level agent configuration without clobbering a target project's generic `do-work` skill.
