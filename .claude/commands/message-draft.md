---
description: "Use to draft a message a person will paste and send: a chat reply, an update to a channel, a PR or issue comment, an email. Puts the point and the ask first, keeps only what supports them, checks it with a linter, and saves it to a file whose path it hands over, so a copy never breaks lines. Triggers include 'draft a message to X', 'write me the reply', 'write that up so I can paste it', and naming a platform such as Slack, Discord, GitHub or email. Never sends anything itself."
argument-hint: "<who it's for and what it's about> [--to slack|discord|github|plain]"
---

# /message-draft

The user sends; this command ends at a draft file. It never posts, emails or comments on anyone's behalf.

## Arguments

- `$ARGUMENTS`: who the message is for and what it is about.
- Optional `--to <platform>`: where it will be pasted: `slack`, `discord`, `github`, or `plain` for anything else, email included. Without it, take the platform from the request when it names one, and use `plain` when it doesn't.

## Steps

1. **Read what you are replying to first.** If this answers a thread, a PR, an issue or an email, read it before drafting: through a tool you have, or ask the user to paste it.
2. **Write two header lines first.** `Point:` is the one takeaway, in one sentence. Two sentences means two messages. `Ask:` is the one action you want from the reader, or `none`.
3. **Shape: bottom line up front.** A lead of one or two lines carrying the Point and the Ask, then at most 3 bullets of evidence, then a link if there is one. 150 words or fewer, at most 2 labels.
4. **Cut.** Remove any line that repeats, hedges or contradicts the lead, or that the reader can't act on. If a later line qualifies the lead, rewrite the lead. Say what an internal name means in plain words, or drop it: the reader hasn't seen your files.
5. **Write like a person.** Plain words, a little warm, no preamble and no sign-off padding. If a `humanizer` skill is available, run it over the message, then put back anything it moved out of the lead.
6. **Format so it survives the paste.**
   - `slack`: `code` and `•` bullets survive. `*bold*` only for short labels (press Cmd+Shift+F after pasting). Never `**bold**`, `_italic_`, `#` headings, `[text](url)`, tables or `<@UID>`; use plain first names.
   - `discord`: Markdown renders, tables don't.
   - `github`: Markdown renders, tables included.
   - `plain`: no markup at all, since email and most other boxes show it raw. Bare URLs, plain `-` bullets.
   - Everywhere: one paragraph per line, never wrapped by hand, since a hand-made break survives the paste. No paragraph over 250 characters, and the whole message under 2,000 characters, the most one Discord message holds on a standard account. If it can't fit, it is two messages: say so and draft both.
7. **Save and lint.** Save to `~/.studio/drafts/YYYY-MM-DD-<platform>-<who>.txt`, with `<who>` as a lowercase, hyphenated slug (`alex-smith`), outside every repository so a draft is never committed: the header, a `---8<---` line, then the message. Each message gets its own file: if that name already holds a different message, the second of a split included, add `-2`, `-3` and so on before `.txt` rather than overwrite it. Run the linter on it and fix what it flags:
   - In a repo that installed Studio: `python3 .studio/source/message_lint.py "<file>" --to <platform>`
   - In the Studio source repo: `python3 studio/message_lint.py "<file>" --to <platform>`

   A clean result means the shape is right, not the argument: reread the lead yourself.
8. **Hand it over.** Give the absolute path, the message itself in a code block, and a command that copies the message without its header: `sed '1,/^---8<---$/d' "<path>" | pbcopy` on macOS. If the draft changes after that, say so and show it again. Once the user says it was sent, add a `SENT` line to the top of the file, with any edits they made.
