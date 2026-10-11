# Optional connections implementation

The offline editor, Windows speech, imports, subtitles and FFmpeg renderer remain independent of connections. Connections start disabled. Only an explicit Test, Generate, Resume or Call action accesses a configured service. Local-only mode restricts HTTP destinations to loopback; online mode permits HTTPS services.

1. Add connection profiles, Windows-protected credentials (environment-variable fallback elsewhere), bounded HTTP transport and persistent generation jobs. Implement Ollama, OpenRouter, OpenAI-compatible text, ElevenLabs speech, ComfyUI API workflows and Runway text-to-video. Save results locally for review; never automatically replace scripts or scene assets.
2. Test provider protocol contracts with a local HTTP fixture, including offline denial, authentication, failures, interruption and resume. These tests do not represent actual model generation.
3. Add actual video scene decoding, trim points, aspect-preserving crop and optional original audio. Verify mixed image/video exports using real FFmpeg/FFprobe.
4. Add Connections UI for profile management, model discovery, prompt review, generation jobs, result review and explicit application to the selected episode. Add generic JSON HTTP and optional MCP tool clients, plus a workspace-scoped Studio MCP server.
5. Exercise desktop controls and integration workflows, run all offline regressions, document setup and distinguish protocol verification from credentialed live-provider verification.

No provider keys, model weights or cloud accounts ship with the application. MCP is an optional dependency and is imported only when requested. External tool descriptions and generated content are data; no automatic tool execution is performed.
