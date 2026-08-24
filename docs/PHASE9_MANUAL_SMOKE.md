# Manual Browser Smoke Checklist

Automated coverage proves module syntax, import integrity, DOM wiring, and
backend contracts. The following **requires a real browser** and must be
verified by hand before declaring the frontend production-ready.

Run the app:

```bash
uvicorn app.main:create_app --factory --reload
# open http://127.0.0.1:8000
```

## 1. Page load
- [ ] Dark glass shell renders; no console errors
- [ ] Topbar shows JARVIS brand, IDLE pill, ONLINE indicator
- [ ] Avatar renders in hero with soft breathing glow (idle)
- [ ] Help "?" popover lists the four commands; clicking one fills the input

## 2. Avatar states
- [ ] Send `help` → brief thinking → speaking waveform → success glow
- [ ] Upload a resume → ANALYZING while parsing → idle on completion
- [ ] Trigger an error (empty message) → controlled red pulse → recovers
- [ ] During a real discovery run: searching → analyzing → matching transitions visible

## 3. Chat
- [ ] User bubble right-aligned; Jarvis bubbles left with rich text
- [ ] `**bold**` / `` `code` `` render; lists render when narrator sends them
- [ ] Typing dots appear while a run is active, removed on reply
- [ ] Action chips appear under result messages and navigate correctly

## 4. WebSocket connection
- [ ] ONLINE pill turns green after connect
- [ ] Kill server → RECONNECTING + red dot → restart → auto-reconnect message

## 5. Agent activity
- [ ] Hero "live step" strip appears during runs with current safe label
- [ ] Clicking it opens the Activity tab
- [ ] Timeline: pending ○ / active ● / completed ✓ in canonical order
- [ ] Completed steps show measured elapsed chips (e.g. `0.4s`)
- [ ] Collapsing the panel shows the current step inline ("● Matching…")
- [ ] Status pill cycles UNDERSTANDING → SEARCHING → … → ✓ COMPLETE
- [ ] No internal node names like `match_candidate_to_jobs` exposed

## 6. Resume upload (PDF · DOCX · TXT · MD)
- [ ] Zone reads "Drop your resume here / PDF · DOCX · TXT · MD / Max 10 MB"
- [ ] Drag-over highlight; browse via click and keyboard (Enter/Space)
- [ ] resume.pdf: file card shows PDF icon, name, size, "Ready";
      progress bar during processing; avatar goes ANALYZING; success stats
- [ ] resume.docx: same flow, "Word document" label
- [ ] resume.txt / resume.md: same flow
- [ ] Change file / Remove buttons reset cleanly
- [ ] Scanned/no-text PDF → "No selectable text could be extracted…" error state
- [ ] Corrupted DOCX → friendly invalid-document message
- [ ] .doc/.png/.zip rejected client-side before upload
- [ ] Oversized file rejected with size message
- [ ] No email/phone or raw document text ever rendered anywhere

## 7. Job workspace
- [ ] After discovery, Jobs tab opens with "JOB MATCHES" header + real counts
- [ ] Cards animate in (first dozen, staggered); reduced-motion disables it
- [ ] Score ring sweeps to its value; tier color correct
- [ ] Matched (✓) and missing (⚠) chips reflect backend arrays only
- [ ] Jobs without matches still render (no silent drops)

## 8. Match drawer ("Why this job?")
- [ ] View Match opens drawer with score, tier badge, matched/missing skills
- [ ] Score breakdown lists components with x/max points + reasons verbatim
- [ ] Escape / ✕ closes; focus moves to close button on open

## 9. Tailor action
- [ ] Tailor Resume chip echoes `tailor job N` as a user message
- [ ] Pill shows TAILORING RESUME; avatar transitions through real events
- [ ] Resume tab populated afterwards

## 10. Resume workspace
- [ ] Document feel: section titles, skill pills, experience cards
- [ ] Why? panels: ORIGINAL → TAILORED → EVIDENCE → reasons from `changes`
- [ ] Unaddressed requirements panel shows count + list when present

## 10b. Validation dashboard
- [ ] Panels titled "RESUME TRUTH" / "ATS READINESS" with severity badges
- [ ] Truth rows read like "✓ T3 — Evidence references consistent"; expandable
- [ ] ATS rows use friendly labels; metrics grid + keyword table render
- [ ] Inflated keyword rows flagged

## 11. Voice input
- [ ] Mic click starts listening (Chrome/Edge); ring animation pulses
- [ ] Interim transcript appears in hero strip
- [ ] Final transcript is sent as chat automatically
- [ ] Second click stops listening early
- [ ] Unsupported browser shows graceful error message

## 12. TTS
- [ ] With Voice checkbox on, replies are spoken; stop button appears and works
- [ ] New user input cancels current speech instantly
- [ ] Checkbox off → no speech, no stop button

## 13. Responsive layout
- [ ] ≥1024px two columns; ≤1023px single column; ≤640px mobile spacing
- [ ] Tabs scroll horizontally on narrow screens; no overflow at 360px
- [ ] Match drawer is full-screen ≤640px
- [ ] All touch targets ≥44px

## 14. Reduced motion
- [ ] OS reduced-motion on: avatar/particles/mic-ring animations disabled
- [ ] State colors, layout and score values remain correct

## 15. Cancellation & replacement
- [ ] Cancel run button visible during a run; clicking stops activity,
      marks the timeline cancelled and hides controls
- [ ] Sending a new request while one runs replaces it with a visible
      replaced-request notice; no stale artifacts leak between runs

## 16. Keyboard navigation & focus
- [ ] Tab order: topbar controls, chat input / mic / send, workspace tabs
- [ ] Upload zone opens the file dialog via Enter or Space
- [ ] Match drawer closes on Escape; close button receives focus on open
- [ ] Help popover closes after choosing an example command
- [ ] Focus-visible outlines appear on every interactive element
