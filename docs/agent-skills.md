# Agent Skills

The shared agent skill source for this repository is `.agents/skills/`.

Codex currently discovers the existing repository skills from `.codex/skills/`.
Those files are preserved for compatibility. Cline discovers project skills from
`.cline/skills/`; Cline's Skills feature may also need to be enabled in Cline
settings.

This repository uses synchronized copies instead of directory symlinks because
the checkout has `core.symlinks=false`, which makes symlink behavior unreliable
on Windows.

## Synchronize Skills

On Windows:

```powershell
.\scripts\sync-agent-skills.ps1
```

On macOS/Linux:

```bash
./scripts/sync-agent-skills.sh
```

Both scripts discover every skill directory in `.agents/skills/`, validate each
`SKILL.md`, and copy the full skill directory into `.cline/skills/`.

## Add A Skill

1. Add the new skill directory under `.agents/skills/<skill-name>/`.
2. Name the instruction file exactly `SKILL.md`.
3. Set frontmatter `name` to the directory name, using lowercase kebab-case.
4. Write a useful `description` that says what the skill does and when it should
   activate. Include both Codex `$skill-name` and Cline `/skill-name` invocation
   forms when documenting explicit invocation.
5. Run the sync script for your platform.
6. If Codex also needs the new skill in this repository, add or synchronize the
   same skill under `.codex/skills/`.
