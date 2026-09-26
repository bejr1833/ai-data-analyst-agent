import { useState } from "react";
import { askDataset } from "../api/client.js";
import AnalysisChart from "./AnalysisChart";
import DataStory from "./DataStory";

export default function AIAnalyst({ datasetId }) {
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);

  /* ==========================================================
     ASK QUESTION
     ========================================================== */

  async function handleAsk(event) {
    event.preventDefault();

    const trimmed = question.trim();

    if (!trimmed || loading) {
      return;
    }

    /* --------------------------------------------------------
       Preserve previous conversation
       -------------------------------------------------------- */

    const conversationHistory = messages.map((message) => ({
      role: message.role,
      text: message.text,
    }));

    /* --------------------------------------------------------
       Add USER message immediately
       -------------------------------------------------------- */

    setMessages((previous) => [
      ...previous,
      {
        role: "user",
        text: trimmed,
      },
    ]);

    setQuestion("");
    setLoading(true);

    try {
      /* ------------------------------------------------------
         Call backend
         ------------------------------------------------------ */

      const result = await askDataset(
        datasetId,
        trimmed,
        conversationHistory
      );

      console.log("AI Analyst result:", result);

      /* ------------------------------------------------------
         Add AI response
         ------------------------------------------------------ */

      setMessages((previous) => [
        ...previous,
        {
          role: "assistant",

          text:
            result.answer ||
            "No answer was returned.",

          rows: Array.isArray(result.rows)
            ? result.rows
            : [],

          visualization:
            result.visualization ||
            null,

          sql:
            result.sql ||
            null,

          resultType:
            result.type ||
            null,
        },
      ]);

    } catch (error) {
      /* ------------------------------------------------------
         Add error message
         ------------------------------------------------------ */

      console.error(
        "AI Analyst error:",
        error
      );

      setMessages((previous) => [
        ...previous,
        {
          role: "error",

          text:
            error.message ||
            "Unable to analyze the dataset.",
        },
      ]);

    } finally {
      setLoading(false);
    }
  }

  /* ==========================================================
     CLEAR CHAT
     ========================================================== */

  function clearChat() {
    setMessages([]);
  }

  /* ==========================================================
     SUGGESTION
     ========================================================== */

  function useSuggestion(text) {
    setQuestion(text);
  }

  /* ==========================================================
     UI
     ========================================================== */

  return (
    <section className="ai-analyst">

      {/* ======================================================
          HEADER
          ====================================================== */}

      <div className="ai-analyst-header">

        <div>

          <div className="ai-analyst-title">
            🤖 AI Data Analyst
          </div>

          <div className="ai-analyst-subtitle">
            Ask questions about your dataset
          </div>

        </div>

        {messages.length > 0 && (
          <button
            className="ai-clear-button"
            onClick={clearChat}
            type="button"
          >
            Clear
          </button>
        )}

      </div>


      {/* ======================================================
          CHAT AREA
          ====================================================== */}

      <div className="ai-analyst-messages">

        {/* ====================================================
            EMPTY STATE
            ==================================================== */}

        {messages.length === 0 && (

          <div className="ai-empty-state">

            <div className="ai-empty-icon">
              ✨
            </div>

            <h3>
              Ask me about your data
            </h3>

            <p>
              Try one of these questions:
            </p>

            <div className="ai-suggestions">

              <button
                type="button"
                onClick={() =>
                  useSuggestion(
                    "What is the total sales?"
                  )
                }
              >
                What is the total sales?
              </button>

              <button
                type="button"
                onClick={() =>
                  useSuggestion(
                    "How many rows are there?"
                  )
                }
              >
                How many rows are there?
              </button>

              <button
                type="button"
                onClick={() =>
                  useSuggestion(
                    "What is the average Sales?"
                  )
                }
              >
                What is the average Sales?
              </button>

            </div>

          </div>

        )}


        {/* ====================================================
            CHAT MESSAGES
            ==================================================== */}

        {messages.map((message, index) => (

          <div
            key={index}
            className={`ai-message ai-message-${message.role}`}
          >

            {/* =================================================
                MESSAGE LABEL
                ================================================= */}

            <div className="ai-message-label">

              {message.role === "user"
                ? "You"
                : message.role === "error"
                ? "Error"
                : "AI Analyst"}

            </div>


            {/* =================================================
                MESSAGE TEXT
                ================================================= */}

            <div className="ai-message-text">
              {message.text}
            </div>


            {/* =================================================
                ANALYSIS CHART
                ================================================= */}

            {message.role === "assistant" &&
              message.visualization &&
              Array.isArray(message.rows) &&
              message.rows.length > 0 && (

                <AnalysisChart
                  rows={message.rows}
                  visualization={
                    message.visualization
                  }
                />

              )}


            {/* =================================================
                DATA STORY
                ================================================= */}

            {message.role === "assistant" &&
              message.visualization &&
              Array.isArray(message.rows) &&
              message.rows.length > 0 && (

                <DataStory
                  result={{
                    type:
                      message.resultType,

                    answer:
                      message.text,

                    rows:
                      message.rows,

                    visualization:
                      message.visualization,
                  }}
                />

              )}

          </div>

        ))}


        {/* ====================================================
            LOADING
            ==================================================== */}

        {loading && (

          <div className="ai-message ai-message-assistant">

            <div className="ai-message-label">
              AI Analyst
            </div>

            <div className="ai-thinking">
              Analyzing your dataset...
            </div>

          </div>

        )}

      </div>


      {/* ======================================================
          INPUT
          ====================================================== */}

      <form
        className="ai-analyst-input"
        onSubmit={handleAsk}
      >

        <input
          type="text"
          value={question}
          onChange={(event) =>
            setQuestion(event.target.value)
          }
          placeholder="Ask a question about your dataset..."
          disabled={loading}
        />

        <button
          type="submit"
          disabled={
            loading ||
            !question.trim()
          }
        >
          {loading ? "..." : "Ask"}
        </button>

      </form>

    </section>
  );
}