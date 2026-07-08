import type { Lesson } from "../types/lesson";
import type { AnswerRecord } from "../types/session";

export function SummaryPanel({
  lesson,
  answerLog,
  completedKnowledge
}: {
  lesson: Lesson;
  answerLog: AnswerRecord[];
  completedKnowledge: string[];
}) {
  const incorrectCount = answerLog.filter((answer) => !answer.isCorrect).length;

  return (
    <section className="panel summary">
      <div className="panel-label">学习总结</div>
      <h2>本次学习完成</h2>
      <p>已完成 {lesson.teaching_steps.length} 个教学步骤。</p>
      <p>答错次数：{incorrectCount}</p>
      <p>建议回顾：极限含义、导数直观意义、切线斜率。</p>
      {completedKnowledge.length > 0 && <p>已覆盖知识点：{completedKnowledge.join("、")}</p>}
    </section>
  );
}

