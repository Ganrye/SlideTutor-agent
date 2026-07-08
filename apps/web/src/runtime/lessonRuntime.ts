import type { Lesson, Slide, SlideElement, TeachingStep } from "../types/lesson";

export function getSlide(lesson: Lesson, slideId: string): Slide | undefined {
  return lesson.slides.find((slide) => slide.id === slideId);
}

export function getElement(slide: Slide | undefined, elementId: string): SlideElement | undefined {
  return slide?.elements.find((element) => element.id === elementId);
}

export function getStepIndex(lesson: Lesson, stepId: string): number {
  return lesson.teaching_steps.findIndex((step) => step.id === stepId);
}

export function getInitialSlideId(step: TeachingStep, fallback: string): string {
  for (const action of step.actions) {
    if ("slide_id" in action) {
      return action.slide_id;
    }
    if (action.type === "jump") {
      return action.target_slide_id;
    }
  }
  return fallback;
}

