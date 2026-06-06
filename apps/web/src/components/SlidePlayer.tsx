import type { Lesson, Slide, SlideElement } from "../types/lesson";
import type { OverlayAction } from "../runtime/actionRuntime";
import { getElement, getSlide } from "../runtime/lessonRuntime";

function bboxStyle(slide: Slide, element: SlideElement) {
  return {
    left: `${(element.bbox.x / slide.width) * 100}%`,
    top: `${(element.bbox.y / slide.height) * 100}%`,
    width: `${(element.bbox.w / slide.width) * 100}%`,
    height: `${(element.bbox.h / slide.height) * 100}%`
  };
}

export function SlidePlayer({
  lesson,
  currentSlide,
  overlays,
  stepLabel
}: {
  lesson: Lesson;
  currentSlide: Slide;
  overlays: OverlayAction[];
  stepLabel: string;
}) {
  return (
    <div className="slide-area">
      <div className="slide-toolbar">
        <span>{currentSlide.title}</span>
        <span>{stepLabel}</span>
      </div>
      <div className="slide-canvas">
        <img alt={currentSlide.title} src={currentSlide.image} />
        {overlays.map((action) => {
          const targetSlide = getSlide(lesson, action.slide_id);
          const targetElement = getElement(targetSlide, action.target_element_id);

          if (!targetSlide || !targetElement || targetSlide.id !== currentSlide.id) {
            return null;
          }

          return (
            <div
              className={`overlay ${action.type}`}
              key={`${action.type}-${action.target_element_id}`}
              style={bboxStyle(currentSlide, targetElement)}
            >
              {action.label && <span>{action.label}</span>}
            </div>
          );
        })}
      </div>
    </div>
  );
}

