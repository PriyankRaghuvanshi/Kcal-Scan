import * as Speech from "expo-speech";

function cleanLine(v) {
  return String(v || "").replace(/\s+/g, " ").trim();
}

export function buildAudioCoachScript({ coachVoice, coachDaily } = {}) {
  const lines = [];
  const greeting = cleanLine(coachVoice?.opening_greeting || coachDaily?.opening_greeting);
  if (greeting) lines.push(greeting);

  const empathy = cleanLine(coachVoice?.empathy_line);
  const insight = cleanLine(coachVoice?.insight_line);
  const oneActionTitle = cleanLine(coachVoice?.one_action?.title);
  const oneActionSteps = Array.isArray(coachVoice?.one_action?.steps)
    ? coachVoice.one_action.steps.map(cleanLine).filter(Boolean).slice(0, 3)
    : [];
  const why = cleanLine(coachVoice?.why_this_action);
  const fallbackSummary = cleanLine(coachDaily?.one_sentence_summary || coachDaily?.coach_summary);
  const fallbackAction = cleanLine(coachDaily?.if_you_do_one_thing || coachDaily?.one_action);

  if (empathy) lines.push(empathy);
  if (insight) lines.push(insight);
  if (oneActionTitle) lines.push(`If you do one thing: ${oneActionTitle}.`);
  if (oneActionSteps.length) lines.push(`Steps: ${oneActionSteps.join(". ")}.`);
  if (why) lines.push(why);

  if (!empathy && !insight && fallbackSummary) lines.push(fallbackSummary);
  if (!oneActionTitle && fallbackAction) lines.push(`Next step: ${fallbackAction}.`);

  return lines.join(" ");
}

export async function stopAudioCoach() {
  try {
    await Speech.stop();
  } catch (_) {}
}

export async function playAudioCoach(script, opts = {}) {
  const text = cleanLine(script);
  if (!text) return false;
  try {
    const speaking = await Speech.isSpeakingAsync();
    if (speaking) {
      await Speech.stop();
    }
  } catch (_) {}

  const speechOpts = {
    pitch: 1.0,
    rate: 0.97,
    language: String(opts.language || "en-US"),
    onDone: typeof opts.onDone === "function" ? opts.onDone : undefined,
    onStopped: typeof opts.onDone === "function" ? opts.onDone : undefined,
    onError: typeof opts.onDone === "function" ? opts.onDone : undefined,
  };
  Speech.speak(text, speechOpts);
  return true;
}
