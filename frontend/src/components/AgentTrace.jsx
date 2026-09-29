import React from "react";

export default function AgentTrace({ agent, sql }) {
  if (!agent || !Array.isArray(agent.plan)) {
    return null;
  }

  return (
    <details className="agent-trace-panel">
      <summary className="agent-trace-summary">
        <span className="agent-trace-chevron">&gt;</span>
        <span>Agent execution trace</span>
      </summary>

      <div className="agent-trace-content">
        {agent.plan.map((step, index) => (
          <div
            key={`${step.tool}-${index}`}
            className="agent-trace-step"
          >
            <div className="agent-trace-step-info">
              <strong>{step.tool}</strong>
              <span> - {step.purpose}</span>
            </div>

            <div className="agent-trace-step-status">
              <span
                className={
                  step.status === "success"
                    ? "agent-trace-status-success"
                    : ""
                }
              >
                {step.status}
              </span>

              {typeof step.duration_ms === "number" && (
                <span>
                  {" | "}
                  {step.duration_ms} ms
                </span>
              )}
            </div>
          </div>
        ))}

        <div className="agent-trace-footer">
          <span className="agent-trace-source-dot" />

          <span>
            {agent.fallback_used
              ? "Gemini fallback"
              : "Local tools"}
          </span>

          <span>|</span>

          <span>{agent.total_duration_ms} ms</span>
        </div>

        {typeof sql === "string" && sql.trim() && (
          <div className="agent-trace-sql">
            <div className="agent-trace-sql-title">
              SQL used
            </div>

            <pre>{sql}</pre>
          </div>
        )}
      </div>
    </details>
  );
}


