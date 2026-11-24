"""Render the import-free Claude Workflow from the portable JavaScript loop."""
from pathlib import Path
from textwrap import dedent

STUDIO = Path(__file__).resolve().parent
WORKFLOW = STUDIO.parent / '.claude/workflows/implementation-loop.js'


def render():
    declarations, body = (STUDIO / 'forge_loop.mjs').read_text().split(
        'export async function runLoop(args, {agent, phase, log}) {\n')
    assert body.endswith('}\n')
    return ('// Generated from studio/forge_loop.mjs by studio/generate_forge.py.\n'
            + declarations + dedent(body[:-2]))


if __name__ == '__main__':
    WORKFLOW.write_text(render())
