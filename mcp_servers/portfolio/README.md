# gigbid-portfolio (MCP server)

Read-only MCP server that answers "what can this freelancer prove?". Tools: `search_evidence`, `get_case_study`, `list_skills`; resources `portfolio://case/{id}` and `portfolio://proposal/{id}`; prompts `answer_screening_question` and `write_cover_letter`. Retrieval is the RAG variant chosen by evaluation (`agent/config.yaml` -> `rag.variant`).

## Install (documented clone + run command; the server reads the persona data in this repo, so it is not a PyPI package)
```bash
git clone https://github.com/msaqibatifj/GigSim.git gigbid && cd gigbid
uv sync && PORTFOLIO_PERSONA=ayesha_ml uv run python -m mcp_servers.portfolio.server
```

## Run
```bash
# from a checkout (stdio, for Claude Desktop / Cursor)
PORTFOLIO_PERSONA=ayesha_ml uv run python -m mcp_servers.portfolio.server
# HTTP
uv run python -m mcp_servers.portfolio.server --http
# Docker
docker build -f infra/docker/python.Dockerfile -t gigbid-portfolio . && docker run -i --rm -e PORTFOLIO_PERSONA=ayesha_ml gigbid-portfolio python -m mcp_servers.portfolio.server
```
Claude Desktop (`claude_desktop_config.json`):
```json
{"mcpServers": {"gigbid-portfolio": {"command": "uv", "args": ["run", "--directory", "/path/to/gigbid", "python", "-m", "mcp_servers.portfolio.server"], "env": {"PORTFOLIO_PERSONA": "ayesha_ml"}}}}
```
Personas (`ayesha_ml`, `bilal_web`, `sara_data`) are synthetic. Add your own case studies as Markdown with front matter (`id`, `type: case_study`, `skills`) under `data/personas/<name>/case_studies/`.
