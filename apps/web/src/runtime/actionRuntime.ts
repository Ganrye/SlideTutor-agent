import type { AnswerRecord } from "../types/session";
import type { GuiAction, Lesson, Question, TeachingStep } from "../types/lesson";
import { getStepIndex } from "./lessonRuntime";

export type OverlayAction = Extract<GuiAction, { type: "highlight" | "mask" }>;

export function getOverlayActions(step: TeachingStep | undefined): OverlayAction[] {
  if (!step) {
    return [];
  }

  return step.actions.filter(
    (action): action is OverlayAction => action.type === "highlight" || action.type === "mask"
  );
}

export function getQuestionForStep(lesson: Lesson, step: TeachingStep | undefined): Question | undefined {
  if (!step) {
    return undefined;
  }

  const action = step.actions.find((item) => item.type === "question_popup");
  return action?.type === "question_popup"
    ? lesson.questions.find((question) => question.id === action.question_id)
    : undefined;
}

export function getJumpTarget(step: TeachingStep | undefined): string | undefined {
  const action = step?.actions.find((item) => item.type === "jump");
  return action?.type === "jump" ? action.target_slide_id : undefined;
}

export function getNextStepIndexAfterAnswer(
  lesson: Lesson,
  question: Question | undefined,
  answer: AnswerRecord,
  fallbackIndex: number
): number {
  const targetStepId = answer.isCorrect ? question?.next_step_id : question?.review_step_id;
  if (!targetStepId) {
    return fallbackIndex;
  }

  const targetIndex = getStepIndex(lesson, targetStepId);
  return targetIndex >= 0 ? targetIndex : fallbackIndex;
}

export function buildCompletedKnowledge(lesson: Lesson, completedStepCount: number): string[] {
  const completedSteps = lesson.teaching_steps.slice(0, completedStepCount);

  return lesson.knowledge_nodes
    .filter((node) =>
      completedSteps.some(
        (step) =>
          step.speech.includes(node.title) ||
          step.actions.some(
            (action) =>
              "target_element_id" in action &&
              node.element_ids.includes(action.target_element_id)
          )
      )
    )
    .map((node) => node.title);
}

