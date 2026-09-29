"""Only used by Playwright. Real API/SQLite with deterministic, keyless providers."""
import asyncio
import os
import tempfile
from pathlib import Path
from uuid import UUID

import uvicorn

from backend.app import create_app
from backend.config import Settings
from backend.contracts import ReviewOutput
from backend.discussion_provider import DiscussionFailure
from backend.reviewer import ReviewFailure


class Reviewer:
    def __init__(self):
        self.calls = {}

    async def review(self, snippet):
        await asyncio.sleep(.3)
        self.calls[snippet.id] = self.calls.get(snippet.id, 0) + 1
        if 'FAIL_ONCE' in snippet.code and self.calls[snippet.id] == 1:
            raise ReviewFailure('Simulated provider failure. Please retry.')
        if 'return a + b' in snippet.code:
            return ReviewOutput(findings=[])
        return ReviewOutput.model_validate({'findings': [{
            'startLine': 2, 'endLine': 2, 'severity': 'warning', 'category': 'bug',
            'description': 'Empty input causes division by zero.',
            'suggestedFix': 'Raise ValueError when the input is empty.',
        }]})


class Discussion:
    def __init__(self):
        self.calls = {}

    async def reply(self, snippet, finding, history, question):
        await asyncio.sleep(.3)
        key = (finding.id, question)
        self.calls[key] = self.calls.get(key, 0) + 1
        if question == 'fail once' and self.calls[key] == 1:
            raise DiscussionFailure('Simulated reply failure. Please retry.')
        return f'Answer with {len(history)} earlier exchanges.\n<script>must remain text</script>\n    Preserve indentation.'


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='snippet-reviewer-e2e-') as directory:
        settings = Settings(database_path=Path(directory)/'test.db', serve_client=True, openai_api_key=None)
        reviewer = Reviewer()
        app = create_app(settings, reviewer=reviewer, discussion_provider=Discussion())

        @app.get('/test/reviewer-calls/{snippet_id}')
        def reviewer_calls(snippet_id: UUID):
            return {"calls": reviewer.calls.get(snippet_id, 0)}

        # Keep the test-only counter ahead of the SPA catch-all mount.
        app.router.routes.insert(0, app.router.routes.pop())
        uvicorn.run(app,host='127.0.0.1',port=int(os.getenv('E2E_PORT', '3032')))
