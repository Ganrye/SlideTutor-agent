import { useEffect, useMemo, useState } from "react";
import { FeedbackPanel } from "./components/FeedbackPanel";
import { QuestionPanel } from "./components/QuestionPanel";
import { SlidePlayer } from "./components/SlidePlayer";
import { SummaryPanel } from "./components/SummaryPanel";
import {
  buildCompletedKnowledge,
  getJumpTarget,
  getNextStepIndexAfterAnswer,
  getOverlayActions,
  getQuestionForStep
} from "./runtime/actionRuntime";
import { getInitialSlideId, getSlide } from "./runtime/lessonRuntime";
import type { TeachingStep, Lesson } from "./types/lesson";
import type { AnswerRecord } from "./types/session";

function App() {
  const [lesson, setLesson] = useState<Lesson | null>(null);
  const [loadError, setLoadError] = useState<string>("");
  const [stepIndex, setStepIndex] = useState(0);
  const [currentSlideId, setCurrentSlideId] = useState<string>("");
  const [answerLog, setAnswerLog] = useState<AnswerRecord[]>([]);
  const [showSummary, setShowSummary] = useState(false);

  useEffect(() => {
    fetch("/data/lesson.json")
      .then((response) => {
        if (!response.ok) {
          throw new Error(`lesson.json 加载失败：${response.status}`);
        }
        return response.json() as Promise<Lesson>;
      })
      .then((data) => {
        setLesson(data);
        const firstStep = data.teaching_steps[0];
        setCurrentSlideId(getInitialSlideId(firstStep, data.slides[0]?.id ?? ""));
      })
      .catch((error: unknown) => {
        setLoadError(error instanceof Error ? error.message : "未知加载错误");
      });
  }, []);

  const currentStep = lesson?.teaching_steps[stepIndex];
  const currentSlide = lesson ? getSlide(lesson, currentSlideId) : undefined;

  const overlays = useMemo(() => getOverlayActions(currentStep), [currentStep]);
  const activeQuestion = useMemo(
    () => (lesson ? getQuestionForStep(lesson, currentStep) : undefined),
    [lesson, currentStep]
  );
  const actionMessages = useMemo(() => {
    if (!currentStep) {
      return [];
    }

    return currentStep.actions.map((action) => {
      if (action.type === "highlight") {
        return `高亮元素：${action.target_element_id}`;
      }
      if (action.type === "mask") {
        return `遮罩元素：${action.target_element_id}`;
      }
      if (action.type === "jump") {
        return `跳转到页面：${action.target_slide_id}${action.reason ? `（${action.reason}）` : ""}`;
      }
      if (action.type === "question_popup") {
        return `弹出问题：${action.question_id}`;
      }
      return `显示反馈：${action.feedback_id}`;
    });
  }, [currentStep]);

  const latestAnswer = answerLog[answerLog.length - 1];
  const latestQuestion = latestAnswer
    ? lesson?.questions.find((question) => question.id === latestAnswer.questionId)
    : undefined;

  function runStepEffects(step: TeachingStep) {
    if (!lesson) {
      return;
    }
    const jumpTarget = getJumpTarget(step);
    if (jumpTarget) {
      setCurrentSlideId(jumpTarget);
      return;
    }
    const slideId = getInitialSlideId(step, currentSlideId || lesson.slides[0]?.id);
    setCurrentSlideId(slideId);
  }

  function goToStep(nextIndex: number) {
    if (!lesson) {
      return;
    }
    const nextStep = lesson.teaching_steps[nextIndex];
    if (!nextStep) {
      setShowSummary(true);
      return;
    }
    setStepIndex(nextIndex);
    runStepEffects(nextStep);
    setShowSummary(nextStep.type === "summary");
  }

  function handleNext() {
    goToStep(stepIndex + 1);
  }

  function handleAnswer(answer: AnswerRecord) {
    setAnswerLog((answers) => [...answers, answer]);

    if (!lesson) {
      return;
    }

    const question = lesson.questions.find((item) => item.id === answer.questionId);
    const nextIndex = getNextStepIndexAfterAnswer(lesson, question, answer, stepIndex + 1);
    goToStep(nextIndex);
  }

  function restart() {
    if (!lesson) {
      return;
    }
    setStepIndex(0);
    setAnswerLog([]);
    setShowSummary(false);
    setCurrentSlideId(getInitialSlideId(lesson.teaching_steps[0], lesson.slides[0]?.id ?? ""));
  }

  if (loadError) {
    return <main className="app-shell error-state">{loadError}</main>;
  }

  if (!lesson || !currentStep || !currentSlide) {
    return <main className="app-shell loading-state">正在加载短期 Demo...</main>;
  }

  const completedKnowledge = buildCompletedKnowledge(lesson, stepIndex + 1);

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">SlideTutor Agent / 短期框架 Demo</p>
          <h1>{lesson.title}</h1>
        </div>
        <button className="ghost" onClick={restart} type="button">
          重新开始
        </button>
      </header>

      <section className="workspace">
        <SlidePlayer
          currentSlide={currentSlide}
          lesson={lesson}
          overlays={overlays}
          stepLabel={`Step ${stepIndex + 1} / ${lesson.teaching_steps.length}`}
        />

        <aside className="sidebar">
          <section className="panel">
            <div className="panel-label">{currentStep.type}</div>
            <h2>{currentStep.title}</h2>
            <p>{currentStep.speech}</p>
            <div className="agent-log">
              <div className="panel-label">Agent 操作日志</div>
              <ul>
                <li>当前页面：{currentSlide.id}</li>
                <li>当前步骤：{currentStep.id}</li>
                {actionMessages.map((message) => (
                  <li key={message}>{message}</li>
                ))}
              </ul>
            </div>
            {!activeQuestion && !showSummary && (
              <button className="primary" onClick={handleNext} type="button">
                Next Step
              </button>
            )}
          </section>

          {activeQuestion && <QuestionPanel onAnswer={handleAnswer} question={activeQuestion} />}

          {latestAnswer && latestQuestion && (
            <FeedbackPanel answer={latestAnswer} question={latestQuestion} />
          )}

          {showSummary && (
            <SummaryPanel answerLog={answerLog} completedKnowledge={completedKnowledge} lesson={lesson} />
          )}
        </aside>
      </section>
    </main>
  );
}

export default App;
