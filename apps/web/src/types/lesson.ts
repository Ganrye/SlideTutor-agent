export type BBox = {
  x: number;
  y: number;
  w: number;
  h: number;
};

export type SlideElement = {
  id: string;
  type: "title" | "text" | "formula" | "diagram" | "note";
  text?: string;
  bbox: BBox;
};

export type Slide = {
  id: string;
  title: string;
  image: string;
  width: number;
  height: number;
  elements: SlideElement[];
};

export type KnowledgeNode = {
  id: string;
  title: string;
  slide_id: string;
  element_ids: string[];
};

export type GuiAction =
  | {
      type: "highlight";
      slide_id: string;
      target_element_id: string;
      label?: string;
    }
  | {
      type: "mask";
      slide_id: string;
      target_element_id: string;
      label?: string;
    }
  | {
      type: "jump";
      target_slide_id: string;
      reason?: string;
    }
  | {
      type: "question_popup";
      question_id: string;
    }
  | {
      type: "feedback";
      feedback_id: string;
    };

export type TeachingStep = {
  id: string;
  type: "explain" | "question" | "review" | "summary";
  title: string;
  speech: string;
  actions: GuiAction[];
};

export type Question = {
  id: string;
  type: "single_choice";
  prompt: string;
  options: Array<{ id: string; text: string }>;
  answer: string;
  feedback: {
    correct: string;
    incorrect: string;
  };
  next_step_id?: string;
  review_step_id?: string;
};

export type Lesson = {
  lesson_id: string;
  title: string;
  source_file: string;
  source_status: "placeholder" | "exported_from_pptx";
  canvas: {
    width: number;
    height: number;
  };
  slides: Slide[];
  knowledge_nodes: KnowledgeNode[];
  teaching_steps: TeachingStep[];
  questions: Question[];
};
