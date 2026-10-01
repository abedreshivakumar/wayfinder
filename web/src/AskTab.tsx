import { useState } from "react";
import { api } from "./api";
import { useAsync } from "./useAsync";

export function AskTab({ repo }: { repo: string }) {
  const [question, setQuestion] = useState("");
  const ask = useAsync(api.ask);
  return (
    <div className="tab narrow">
      <p className="muted">Sends your question and what the tools find to Claude. Needs offline mode off and this repo on the allowlist.</p>
      <textarea rows={4} placeholder="e.g. What happens when a user logs in?" value={question} onChange={(e) => setQuestion(e.target.value)} />
      <div className="row"><button disabled={!repo || !question.trim() || ask.loading} onClick={() => ask.run(repo, question)}>{ask.loading ? "Thinking..." : "Ask"}</button></div>
      {ask.error && <p className="error">{ask.error}</p>}
      {ask.data && <div className="answer"><p>{ask.data.text}</p><p className="muted">Tools used: {ask.data.tools_used.join(", ") || "none"}</p></div>}
    </div>
  );
}
