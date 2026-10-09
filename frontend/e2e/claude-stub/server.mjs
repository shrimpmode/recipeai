// Minimal stand-in for the Anthropic Messages API, used only by the E2E stack.
// It answers like Claude would for queries.services.generation.LLMPicker: a call
// to the structured output tool Pydantic AI offers, picking the first three
// candidates it was given.
import { createServer } from "node:http";

const server = createServer(async (request, response) => {
  if (request.method !== "POST" || !request.url?.startsWith("/v1/messages")) {
    response.writeHead(404).end();
    return;
  }
  let raw = "";
  for await (const chunk of request) raw += chunk;
  const body = JSON.parse(raw);
  const content = body.messages[0].content;
  const text = typeof content === "string" ? content : content.map((block) => block.text ?? "").join("");
  const { candidates } = JSON.parse(text);
  const picks = candidates.slice(0, 3).map((candidate) => ({
    recipe_id: candidate.recipe_id,
    description: `Stub pick: ${candidate.recipe_name}.`,
  }));

  response.writeHead(200, { "content-type": "application/json", "request-id": "req_e2e_stub" });
  response.end(
    JSON.stringify({
      id: "msg_e2e_stub",
      type: "message",
      role: "assistant",
      model: body.model,
      content: [{ type: "tool_use", id: "toolu_e2e_stub", name: body.tools[0].name, input: { response: picks } }],
      stop_reason: "tool_use",
      stop_sequence: null,
      usage: { input_tokens: 0, output_tokens: 0 },
    }),
  );
});

server.listen(8080, () => console.log("claude stub listening on :8080"));
