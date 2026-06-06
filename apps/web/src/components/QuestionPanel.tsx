import { useState } from "react";
import type { Question } from "../types/lesson";
import type { AnswerRecord } from "../types/session";

export function QuestionPanel({
  question,
  onAnswer
}: {
  question: Question;
  onAnswer: (answer: AnswerRecord) => void;
}) {
  const [selected, setSelected] = useState<string>("");

  return (
    <section className="panel question-panel">
      <div className="panel-label">主动提问</div>
      <h2>{question.prompt}</h2>
      <div className="option-list">
        {question.options.map((option) => (
          <button
            className={selected === option.id ? "option selected" : "option"}
            key={option.id}
            onClick={() => setSelected(option.id)}
            type="button"
          >
            {option.text}
          </button>
        ))}
      </div>
      <button
        className="primary"
        disabled={!selected}
        onClick={() =>
          onAnswer({
            questionId: question.id,
            selectedOptionId: selected,
            isCorrect: selected === question.answer
          })
        }
        type="button"
      >
        提交回答
      </button>
    </section>
  );
}

