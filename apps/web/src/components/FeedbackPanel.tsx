import type { Question } from "../types/lesson";
import type { AnswerRecord } from "../types/session";

export function FeedbackPanel({
  answer,
  question
}: {
  answer: AnswerRecord;
  question: Question;
}) {
  return (
    <section className={answer.isCorrect ? "panel feedback correct" : "panel feedback incorrect"}>
      <div className="panel-label">反馈</div>
      <p>{answer.isCorrect ? question.feedback.correct : question.feedback.incorrect}</p>
    </section>
  );
}

