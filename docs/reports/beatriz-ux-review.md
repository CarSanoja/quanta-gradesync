# GradeSync, walked through by Beatriz Rojas

Mathematics, 31 years in the classroom. Written 26 August 2026.

I was asked to use this the way I would really use it and to write down everything. I did not
guess: I had the program running on my own machine and I went through every screen, including
the mornings when things go wrong. Where I say something is broken, I name the file and the line
so somebody can find it.

I will say the good part first, because it is real and I do not want it lost in the rest. The
words on these screens are written for a person, not for a computer. "We held 15 exams for you."
"Something on these pages the system will not decide on its own." The review screen puts the
scanned page next to the marks and quotes the line it read. The type is big enough for my eyes.
When I released twelve exams in one go, it worked, it told me it worked, and both buttons went
grey while it was working so I knew not to press again. That part I trust.

The rest of this report is about everything else.

---

## 1. The journeys

Twenty-nine of them. I have numbered them and said, for each, what I wanted, what I did, what the
screen did, and where I stopped.

### Sending

**1. I open GradeSync for the first time, having sent nothing.**
I wanted to see what this is. The page says "Nothing needs you.", tells me marking costs about
five minutes an exam and that two hundred exams a month is eighteen hours, and offers a box to
drop scans into. This is fine. It is the one screen that does exactly what it promises.

**2. I send a class whose files are already named. This is the journey that loses my work.**
My files are `ana-torres.jpg`, `bruno-diaz.jpg`, and so on. I choose them. A grey message slides
in at the bottom: "Say which subject, class and assessment these scans belong to." Three boxes
appear at the top. I fill them in — Mathematics, 10B, Quiz 3 — carefully, because I am careful.
The page then says, in plain words:

> **0 of 3 files have arrived.**
> *You can leave this page — sending continues on its own.*

So I leave. **Nothing was ever sent.** Not one byte. I watched the network for six seconds after
filling the last box and there was not a single request. The three exams are still sitting on my
laptop and the page told me I could walk away.

The cause is `teacher-upload.js:103-109`. `setLotField` writes the value and redraws the screen,
and that is all it does. It never calls `runQueue`. Sending is only ever started from five places
— `stageFiles` (`teacher-upload.js:286`), the rename timer (`teacher-upload.js:99-100`),
`answerPair` (`:127`), `retryFailed` (`:227`), and the "Done" button (`teacher.js:88`). Filling in
the three boxes is not one of them. The first attempt, from `stageFiles`, already gave up at
`teacher-upload.js:190-198` because there was no assessment yet, and nothing goes back to try
again.

The message telling me to leave is `teacher-uploading.js:143-145`. The message telling me to fill
the boxes lives for 4.6 seconds and then vanishes (`teacher-dialogs.js:6`), so by the time I have
typed three words it is already gone and the page has switched to telling me it is all under
control.

The only escape is the "Done — start grading" button at the bottom of the page. I did not press
it, because the page had just told me sending continues on its own.

**3. I send photographs taken with my telephone.**
The files are `IMG_4021.jpg` and so on. The page correctly says it cannot tell whose they are and
asks me to type each name, with a thumbnail beside each one. That is thoughtful. But at that same
moment, with nothing sent and no assessment named, the page already says *"You can leave this page
— sending continues on its own."* (`teacher-uploading.js:145`). It says that because
`uploads.awaitingLot` is still false: the first attempt to send gave up one line earlier, at
`teacher-upload.js:187`, before it could set the flag, because no file was ready yet.

If I type the names first and fill in the three boxes afterwards — which is the natural order,
since the names are what the page is shouting about — I land in exactly the dead end of journey 2.
If I happen to fill the boxes first, the 900-millisecond timer after my last name
(`teacher-upload.js:99-100`) starts the sending and everything works. Whether my class of exams is
sent or silently abandoned depends on which of two boxes I filled in first. Nothing on the screen
tells me that.

**4. I press "Done — start grading" on a class of thirty-six.**
I pressed it and watched. At the instant of the click, the screen showed me:

> ## Nothing needs you.

That is the home screen, with the sales line about eighteen hours a month, while thirty-six of my
exams are being sent one at a time behind it. The cause is `teacher.js:82-84`: pressing the button
clears the screen and marks the upload as dismissed, then starts sending without waiting and asks
the server for a fresh summary. The redraw happens immediately with the old summary, which has no
batch in it, so `defaultScreen()` (`teacher-state.js:73-90`) falls through to "home".

About a second later it changed to "We received 36 exams." In production a class of thirty-six
takes around thirty-four seconds to send, one file at a time. For all of those thirty-four seconds
there is no bar, no count, no "19 of 36 sent" — the progress bar was on the screen I was just
thrown off, and `teacher.js:287-289` will not bring that screen back once the upload has been
dismissed. The button itself does not go grey and does not change its words
(`teacher-uploading.js:157`).

I pressed a large button on thirty-six exams and the computer said "Nothing needs you." I would
assume I had lost them.

**5. My scanner names files in a sequence. The page tells me my whole class is one exam.**
The machine in the staff room saves `student-01.jpg` through `student-36.jpg`. I chose all
thirty-six. The page stopped everything and said:

> ### Some files look like one exam
> student-01.jpg and student-02.jpg and student-03.jpg and student-04.jpg and … and student-36.jpg
> look like pages of the same exam.

Eight hundred and three characters, one sentence, thirty-five "and"s. Underneath, two buttons:
"One exam — I'll send them as one PDF" and **"Two different students"** — for thirty-six files.
All thirty-six exams were frozen and "Done — start grading" refused to work, saying "Some files
still need an answer from you before they can be sent."

The cause is `teacher-filenames.js:13`. The pattern `BARE_NUMBER` treats anything ending in a dash
and a number as page N of a document called by the part in front, so all thirty-six share the base
"student" and `detectPageGroups` (`teacher-filenames.js:66-88`) returns them as one group. I
checked `10a-01.jpg` … `10a-36.jpg` too: same result, one group of thirty-six. The button text is
hard-coded for two files at `teacher-uploading.js:41` and `:47`.

If I pressed the first button — which is the highlighted one, and reads like the safe answer — all
thirty-six of my exams would be marked "held back" with a note telling me to rescan the class into
a single PDF (`teacher-upload.js:118-121`).

**6. Two files really are the two pages of one exam.**
`ana-torres-p1.jpg` and `ana-torres-p2.jpg` are correctly spotted as one exam, and the wording is
clear. This works.

**7. I send the same batch twice because I was not sure it went through.**
Four files, four separate boxes, one after another, each one asking whether to replace or keep. I
counted them: four modals for four files. For a class of thirty-six that is thirty-six boxes. None
of them says how many more are coming — the heading is just "This student already has a scan"
(`teacher.html:60`). I have no idea, on the first one, whether I am agreeing to one more or to
thirty-five more.

**8. I notice the tick-box.**
There is a box at the bottom of that dialog: "Do the same for the rest of this batch". I ticked it
on the first one and answered once for all four. This works and it is the right idea. But it is
unticked every single time the box opens (`teacher-dialogs.js:75`), so if I do not notice it on
the very first modal — and it is below the buttons, which is where I stop reading — I answer all
thirty-six.

**9. The school internet dies halfway through sending.**
I sent eight; three got through and then the connection went. The page said:

> **All 8 files arrived.**

with the bar full. Five of them never left my laptop. `uploadState` counts a failure as something
that has "arrived" (`teacher-upload.js:10` and `:40`), and `teacher-uploading.js:126-128` turns
that count into the sentence. Underneath, further down where I have to scroll, there is a panel
saying "5 files did not go through" with "we couldn't reach GradeSync" beside each one — listed by
file name, not by student name — and a "Try those again" button. The note in the middle of the
page still says sending continues on its own.

**10. I remember one more exam and add it. The five failures vanish.**
Having those five failures on the screen, I picked one extra file I had forgotten. The failure
panel disappeared, the retry button disappeared, and the list of what never arrived was gone. I
verified this: three failed rows, I added one file, and the page showed one row and no memory of
the three. The cause is again that a failure counts as "sent", so `uploadState().finished` is true
(`teacher-upload.js:54`) and `stageFiles` throws everything away at `teacher-upload.js:275-277`.

Those three students have no grade and there is nothing anywhere to tell me so.

### Waiting

**11. I wait while it grades.**
The grading screen says: *"This page keeps itself up to date. You can close it and come back —
grading carries on without you."* (`teacher-screens.js:110-112`).

It asks the server every six seconds and stops after sixty tries — six minutes — and then says
nothing (`teacher.js:21-22` and `:230`). After six minutes the page is a photograph. It still says
it keeps itself up to date.

Worse: it only refreshes at all if there is a batch on the screen. `schedulePoll`
(`teacher.js:228-231`) decides it is busy only when `activeBatch()` exists. I opened the page with
fifteen exams waiting for me and no batch showing, and measured: **zero requests in twenty
seconds.** Not one. If somebody finishes grading, or another exam is held, my page will never
know.

### The next morning

**12. I come back the next morning and something needs me.**
The page opens straight onto "We held 15 exams for you." with the reasons in plain words. Good.
But nowhere on that screen does it say *which class or which exam these are*. The little line
above the heading says "On hold" and the line at the top of the window is empty. That is
`teacher-held.js:96` falling back to the words "On hold" because there is no batch, and
`contextLine` (`teacher-state.js:99-112`) returning an empty string for the same reason. I teach
five classes. Fifteen exams are waiting and I cannot tell whose.

The twelve held "as a precaution" are not listed at all (`teacher-held.js:64-87`). I am asked to
put twelve grades into the gradebook without being shown a single name.

**13. I decide on the ones it would not grade.**
This screen is the best thing here. The scan on the left, the reason it stopped, the line it read
from the page, the marks it proposes, what the student will see, and three clear choices. I have
no complaint about the content.

**14. I change a mark before accepting.**
"Change the marks" turns each line into minus and plus buttons in half-point steps, the total
recalculates as I press, and the main button changes its words to "Save these marks to the
gradebook". This works and it is well done. The button goes grey while it saves.

**15. I say "I'll grade this one myself".**
Works, and the message afterwards is honest: "…came back to you — no grade was recorded."

**16. I need to look at one particular student's exam. I cannot.**
Olga Vera's mother is on the telephone. Three exams are waiting; Olga is the third. Her name is on
the list in front of me. I clicked it. Nothing — the rows are not buttons (`teacher-held.js:46-49`).
The only way in is "Review these one at a time", which always opens the first one
(`teacher.js:61`). On the review screen there is no "next", no "previous", no "skip" — I checked,
the only things there are "Stop for now", "See it bigger" and the three decisions
(`teacher-review.js:200-212`). To reach Olga I would have to make a real decision about Marta and
a real decision about Néstor first. I will not do that with a parent on the phone, so I stop.

There is a search box, but only when more than eight exams are waiting (`teacher-held.js:43`), and
even then it only filters the little list — it does not change where "Review these one at a time"
starts. I confirmed this in the code and on the screen.

**17. I want to go through them in the order I sent them.**
There is no such order available. The queue is whatever order the grading finished in
(`core/review/store.py:57`, sorted by when the review was created), and I cannot move within it
anyway. Once I have decided on an exam it is gone from the queue and there is no way back to look
at what I did.

**18. I release the whole batch.**
"Put all 12 in the gradebook" opens a clear question — what will happen, that the three needing my
judgement stay behind, and a yes button that repeats the number. Both buttons grey out while it
works and a message confirms "12 exams are in the gradebook." This is the best-behaved action in
the product. The button keeps its old words while it works; "Putting them in…" would be kinder,
but I knew what was happening.

### Looking things up

**19. I look up one student's mark.**
"Recent grades" in the top corner, a search box, one row per student with the score and when it
went into the gradebook. Fine for this week. It loads the fifty most recent
(`api.js:101-107`, `sis_ledger.py:17`) and the search only looks inside those fifty
(`teacher-screens.js:167-169`). I mark two hundred exams a month. From the third week onward, a
student I search for who is not in the last fifty simply does not exist, and the page says nothing
about why.

**20. I open a grade to see how it was made up. The ones I decided are empty.**
The rows open now, which is new. For an exam the machine graded on its own I get:

> How this grade was made up
> Crit a — 3.6 — read with 95% confidence

For an exam that **I** released, I get nothing at all: no heading, no marks, just the curriculum
code and two timestamps. I checked the data behind it — three of my fifteen records carried a
breakdown and twelve did not, and the twelve were exactly the ones I decided. `breakdown()`
(`teacher-grades.js:21-26`) only draws the section when the record carries criterion scores, and
the records written by approving and releasing do not carry them. The exams I put my name to are
the ones with no explanation.

Also, the line says "Crit a", not "Reasoning". It is showing me the internal code for the
criterion, tidied up (`teacher-grades.js:6-8`), instead of the words I wrote in the rubric.

**21. I finish the last exam. Where do I land?**
On "Nothing needs you.", with the sales paragraph about eighteen hours a month. No "Parcial 1 is
finished", no tally of what I just did, no count of how many were graded without me. I had just
worked through the whole thing and the computer greeted me like a stranger.

There *is* a finished screen — "…is finished", with a tally and a class average
(`teacher-screens.js:133-164`). I could not reach it. It requires both that the batch be settled
*and* that `state.following` be true (`teacher-state.js:86`), and `state.following` starts false
on every fresh page load unless the address has a `?batch=` in it (`teacher-state.js:18`), which
nothing in the product ever puts there. So the completion screen cannot be reached the next day.

The band that is supposed to tell me how many were graded without me could not appear either,
because it needs a batch and there was none. I got the advertisement instead.

### Getting back, and getting in

**22. "I came out by accident — how do I get back to the batch?"**
There is no control anywhere for choosing a batch. Which one I am looking at is a variable inside
the page (`state.lotCode`, `teacher-state.js:9`) and the only two buttons at the top are "Recent
grades" and "Send scans" (`teacher.html:19-20`). The address bar never changes.

It is worse than "only three recent batches". The list of recent batches
(`teacher.py:92-104`) is built only from jobs that have actually run, and each one is then thrown
away unless files can also be counted under the upload folder (`teacher_batch.py:38-39` and
`:140-144`). In my run those two conditions never overlapped and **the list came back empty** — no
recent batches at all, even though I had just sent thirty-six exams and graded another batch.

So there is no way back, and the fallback that was supposed to save me was empty too.

One mercy: the page *does* read `?batch=` from the address when it starts (`teacher-state.js:9`).
I typed a batch code into the address by hand and the batch came straight back, with the right
screen and the right heading. The machinery for going back already exists. Nothing ever writes the
address, so nobody can ever use it.

**23. I close the tab by accident, or open it in a new one.**
The access code is kept in `sessionStorage` (`api.js:13` and `:17`), which is emptied the moment
the tab closes. Every new tab asks me for the school's access code again, with the box empty. I do
not know that code by heart. I would have to find the email.

**24. I press Cancel at the access code box because I cannot find the code.**
The box closes and I am left looking at **a completely blank white page** — no words, no button,
nothing (`teacher-dialogs.js:178` just hides it). I verified this: the main area is empty. I would
think I had broken it. The only way back is to know to reload the page.

Typing the wrong code does behave properly: the box reopens and says "That access code didn't
work. Check it and try again."

**25. The internet is down when I open the page.**
A decent screen: "We could not load your page.", "Nothing was lost — grading carries on.", and two
buttons. But at the same time a grey message slides in at the bottom saying, on its own:

> **fetch failed**

That is `teacher-actions.js:21` showing me the error the browser handed it. Two English words that
mean nothing to me and look like the sort of thing that appears just before you lose everything.

**26. I press "Send scans" while a batch is still grading.**
This is the strangest screen in the product. With thirty-six exams received and none yet in the
gradebook, the page said:

> ## Nothing needs you.
> All **0** exams from Parcial 2 are in the gradebook, and your students can see their feedback.
> null
> [Drop your scans here]
> Last sent — 36 exams, Parcial 2.

Three separate faults on one screen:
- "All 0 exams … are in the gradebook, and your students can see their feedback" for a batch where
  nothing is in the gradebook. `renderHome` (`teacher-screens.js:44-48`) writes that sentence
  whenever a batch exists at all, without checking whether anything is finished.
- The word **`null`** printed on the page. `valueBand` returns nothing when no exam has been
  graded automatically yet (`teacher-value.js:20-23`) and `renderHome` hands that straight to the
  page (`teacher-screens.js:52`), which prints it as the word "null". I verified this both in
  isolation and through the running program.
- "Last sent — 36 exams" with a dash and then nothing, because a batch that has only been uploaded
  has no start time (`teacher.py:123`, `teacher-screens.js:61-64`).

If I saw this after sending a class I would assume the system had eaten my thirty-six exams.

**27. I open it on my telephone.**
There is one size change in the whole stylesheet (`teacher.css:514`). Below it the review screen
stacks, which puts the full-width photograph of the exam first and the three decision buttons at
the very bottom — so on a telephone I scroll past the whole scan every time to reach the buttons,
and cannot see the marks and the page at once, which is the entire point of that screen. The file
chooser is a plain file input with no camera option (`teacher.js:271-276`), so on a telephone it
opens the file browser rather than the camera.

**28. I press the Back button, or try to bookmark this.**
Nothing happens. There is no address for any of it — I searched the whole teacher surface and
there is not a single `pushState`, `hash` or `popstate`. I cannot bookmark the list of exams
waiting for me, I cannot send my head of department a link to a batch, and the browser Back button
does nothing at all. When I press Back out of habit I leave GradeSync entirely.

**29. I want to know something needs me without opening the page.**
There is nothing. No mail, no bell, no count. And the name of the window is fixed in the file as:

> `<title>GradeSync — Nothing needs you</title>` (`teacher.html:6`)

I keep a dozen tabs open. That tab says "Nothing needs you" while fifteen exams need me. It is
never anything else.

---

## 2. Every error and every wait

| # | What sets it off | What I see | What I understand | What I do | What it should say |
|---|---|---|---|---|---|
| E1 | I fill the three assessment boxes after choosing files (`teacher-upload.js:103-109`) | "0 of 3 files have arrived." + "You can leave this page — sending continues on its own." | It is sending. I can go. | Leave. Lose the class. | Start sending the moment the third box is complete — or say "Not sent yet. Press Send." |
| E2 | I press "Done — start grading" (`teacher.js:82-84`) | "Nothing needs you." for about a second | My click did nothing, or it lost them | Press again, or panic | Stay on the sending screen with a real count until the last file is up |
| E3 | Sending 36 files, ~34 seconds in production | No bar, no count, nothing (`teacher.js:287-289`) | It is stuck | Wait, then reload — which is when I might lose them | "Sending 19 of 36 — about 16 seconds left" |
| E4 | Internet dies mid-send | "All 8 files arrived." with a full bar (`teacher-uploading.js:126-128`) | Everything went through | Close the page. Five students have no grade. | "3 of 8 arrived. 5 could not be sent." Failures must never count as arrivals. |
| E5 | I add another file after some failed (`teacher-upload.js:275-277`) | Failure list and retry button silently vanish | There was nothing wrong | Never retry them | Keep failures until I dismiss them by name |
| E6 | Files named in a sequence (`teacher-filenames.js:13`) | An 803-character sentence claiming 36 files are one exam; everything frozen | The computer is confused, and I might break it | Stop | Never group more than a handful; ask per pair, and say "36 separate students" on the button |
| E7 | Same batch sent twice | One box per file, no idea how many follow (`teacher.html:60`) | This will never end | Click through blindly | "Ana Torres already has a scan — 1 of 36" and remember my answer by default |
| E8 | Page loads with no internet | Grey message: **"fetch failed"** (`teacher-actions.js:21`) | Something serious has broken | Call someone | "GradeSync could not be reached. Your work is safe." Never show the browser's own words. |
| E9 | Six minutes on the grading screen (`teacher.js:21-22`) | Nothing changes, ever; still says "This page keeps itself up to date" | It is still working | Sit there | "Still checking…" or "Paused — press to check again" |
| E10 | Exams waiting but no batch on screen (`teacher.js:228-231`) | No refresh at all — I measured zero requests in twenty seconds | It is live | Stare at a dead page | Refresh whenever anything is waiting |
| E11 | Loading a scan in review (`teacher-review.js:190`) | "Loading the scanned page…" as plain grey text | Fine, if it is quick | Wait | Keep it, but add a real skeleton — and stop fetching the same image twice, which it does on every open |
| E12 | Home screen, batch not finished (`teacher-value.js:20-23` → `teacher-screens.js:52`) | The word **`null`** on the page | The program is broken | Stop trusting it | Print nothing |
| E13 | Home screen, batch still grading (`teacher-screens.js:44-48`) | "All 0 exams … are in the gradebook, and your students can see their feedback" | My exams have gone missing | Panic | "36 sent, still grading. Nothing needs you yet." |
| E14 | Cancel at the access code (`teacher-dialogs.js:178`) | A blank white page | I have broken it | Reload, or give up | Keep the code box, or show "GradeSync needs your access code" with a button |
| E15 | New tab or reopened browser (`api.js:13`) | Access code box, empty | It has forgotten me again | Go looking for the email | Remember the code on this device |
| E16 | Batch held, no batch identified (`teacher-held.js:96`) | "On hold", empty heading line | Which class? Whose exams? | Guess | Always name the subject, class and assessment |
| E17 | 12 held as a precaution (`teacher-held.js:64-87`) | A count and no names | I am signing for twelve unknown grades | Release blindly, or not at all | List them, even collapsed |
| E18 | Opening a grade I released (`teacher-grades.js:21-26`) | No breakdown at all | The detail is only there sometimes | Distrust the feature | Carry the marks through on approve and release |
| E19 | Searching for a student from last month (`api.js:101-107`) | "No student here matches…" | She has no grade | Doubt the gradebook | "Not in the 50 most recent — search all" |
| E20 | Any click at all (`teacher.css`) | No pressed state anywhere — there is not one `transition` in the stylesheet | Did it register? | Click again | Something must move on press |

---

## 3. Navigation and memory

### Why I cannot get back to what I was doing

Four separate mechanisms, each on its own enough to trap me.

1. **There is no address.** No `pushState`, no hash, no `popstate` anywhere in the teacher files.
   The address bar shows `/teacher` from the first second to the last. Back does nothing, nothing
   can be bookmarked, nothing can be sent to a colleague.

2. **Which batch I am looking at is a variable, not a place.** `state.lotCode`
   (`teacher-state.js:9`) is set when I upload, and when I make a decision (`teacher-actions.js:98`).
   There is no control anywhere to choose a different one — the top of the window has exactly two
   buttons, "Recent grades" and "Send scans" (`teacher.html:19-20`).

3. **The list of recent batches is nearly always useless.** At most three
   (`teacher.py:28`), built only from jobs that have already run (`teacher.py:92-104`), and then
   each is discarded unless files can also be counted under the upload folder
   (`teacher_batch.py:140-144`) — a folder computed from a *different* identity than the job's
   (`teacher_batch.py:38-39`). In my run the list came back **empty** after uploading 36 exams and
   completing a graded batch.

4. **Which screen I land on is a guess.** `defaultScreen()` (`teacher-state.js:73-90`) works down a
   ladder: a named unfinished batch, then anything waiting, then a finished batch but only if I am
   "following" it, otherwise home. Since "following" resets to false on every fresh load
   (`teacher-state.js:18`), the finished screen can never be reached the next morning, and the
   first thing I see is decided for me by a rule I cannot see or change.

The cruel part: `teacher-state.js:9` already reads `?batch=` from the address. I typed a batch code
in by hand and everything came back correctly. The way home exists. It is simply never written
down.

### What I would put in its place

**Give things addresses.** Four are enough:

- `/teacher` — what needs me, across everything
- `/teacher?batch=2026_matematicas_10A_Parcial1` — one batch
- `/teacher?batch=…&review=ana-torres` — one exam, open
- `/teacher?grades=ana-torres` — one student's marks

Write the address with `pushState` whenever the batch, the screen or the open exam changes, and
listen for `popstate` so Back walks back through what I did. Everything needed to read those
addresses already exists; only the writing is missing. Then I can bookmark "the exams that need
me", the Back button behaves, and I can send my head of department a link.

**A place for what needs me, and a count I can see without opening the page.**
- The count belongs in the window title: `(15) GradeSync — 15 exams need you`, instead of the
  fixed "Nothing needs you" at `teacher.html:6`. That alone changes my whole day, because I keep
  the tab open.
- The top of the window should carry a third button — "Needs me (15)" — beside the two that are
  there, always visible, on every screen.
- That screen should be one list of everything waiting, from every class, each row saying the
  student, the class, the assessment, the reason and how long it has waited — and **every row
  clickable**, straight to that exam. Today the rows are dead (`teacher-held.js:46-49`) and I must
  decide on two other people's exams to reach the third.

**Coming back to a batch, in the order I sent them.**
- The batch list must be built from what I have actually sent, not only from jobs that have run,
  and it must not be thrown away when one of two folder-name guesses disagrees
  (`teacher_batch.py:140-144`).
- Show more than three, with the date and the assessment name, reachable from "Recent grades".
- Inside a batch, list every exam in the order it was sent, with its state — in the gradebook,
  waiting for me, could not be graded — and let me open any one of them. That is what "revisit
  them in the order we sent them" means, and it does not exist today in any form.
- In review, add "next" and "previous" that move without deciding, and let me reopen an exam I
  already decided so I can check myself.

---

## 4. What the screens promise, and what they deliver

I was asked to be concrete rather than say I do not like it. Here is what I can point at.

**Nothing on this page ever moves.** I searched the whole stylesheet: there is not one
`transition` and not one `animation`. The only mention of motion is `teacher.css:525-527`, which
politely turns off animations for people who dislike them — animations that do not exist. So:
- No pressed state on any button. `.primary` changes colour on hover (`teacher.css:105`) and dims
  when disabled (`:106`), and that is the whole vocabulary. When I press "Done — start grading" on
  thirty-six exams (journey 4), the button does not react at all, and the screen behind it
  changes to "Nothing needs you." My click produced no acknowledgement whatsoever.
- Screens replace each other instantly, with nothing carried across. "We held 15 exams for you"
  and "Nothing needs you." arrive with the same violence.
- The progress bar (`teacher.css:233`) has no transition, so it jumps in steps.

**Nothing tells me the machine is working.** There is no spinner, no skeleton, no busy state
anywhere in the stylesheet. The only two "working" signals in the whole product are the grey
buttons in the release dialog (`teacher-actions.js:119`) and the grey text "Loading the scanned
page…" (`teacher-review.js:190`). Every other wait is a still page.

**The progress that does exist is not honest.** The bar fills as files "arrive", and a file that
failed counts as arrived (`teacher-upload.js:10`). A full bar and "All 8 files arrived" is what I
was shown when five of them had not. An honest bar would have three colours: sent, sending, could
not send.

**There is no sense of speed anywhere, and speed is the whole product.** In production this grades
thirty-six exams in about three minutes for about sixty-four cents, and thirty-two of them never
need me at all. I never see that happening. I see a static list — "0 are already in the gradebook",
"36 are still being graded" — that changes every six seconds without any indication that it
changed, and then stops changing after six minutes without saying so. The one moment the product
could show me what it is worth is the moment it goes quiet.

**The value band arrives at the wrong moment.** On a first visit it tells me marking costs five
minutes an exam and that I could save eighteen hours a month. That is fine before I have used it.
But after I finished reviewing every exam (journey 21) I was sent back to that same advertisement,
because the band that says "32 of 36 were graded without you" needs a batch and there was none.
The moment I have earned that sentence is the exact moment it is replaced by a sales pitch.

**The type and colour are good; the hierarchy is not.** Large serif headings, a warm paper
background, generous line height, a visible focus ring (`teacher.css:52`), proper disabled states.
I can read it, which is more than I can say for the ministry portal. But everything on a screen has
the same weight: on the held screen, "Review these one at a time" and "Put all 12 in the gradebook"
look equally important, and one of those puts twelve grades in front of students permanently.

**On a telephone** (journey 27) there is a single size change at `teacher.css:514`. The review
screen stacks the scan above the decisions, so the two things I must compare cannot be seen
together, and the buttons are a full screen of scrolling away.

---

## 5. What to fix, in order

### (a) Things that lose my work or trap me — fix these first

| Fix | Where | Under an hour |
|---|---|---|
| Start sending as soon as the three assessment boxes are complete: call `runQueue(false)` from `setLotField` when `lotCodeNow()` is truthy | `teacher-upload.js:103-109` | **yes** |
| Never say "sending continues on its own" unless something is actually in flight; when nothing is, say "Not sent yet" and show the Send button | `teacher-uploading.js:143-145` | **yes** |
| Stop counting failures as arrivals — take `"failed"` out of `SENT` and count it separately in the headline and the bar | `teacher-upload.js:10`, `teacher-uploading.js:126-128` | **yes** |
| Stop wiping failed rows when I add another file: keep any row that failed across `resetUploads` | `teacher-upload.js:275-277` | **yes** |
| Cap page-grouping at, say, three files and require an explicit `p1/p2` marker for more, so a class never collapses into "one exam" | `teacher-filenames.js:13`, `:66-88` | **yes** |
| Keep the sending screen on screen until the last file is up, instead of jumping to "Nothing needs you." | `teacher.js:82-84` | **yes** |
| Write the address on every change and read it back on Back — `?batch=`, `?review=` (the reading half already works) | `teacher.js`, `teacher-state.js:9` | no |
| Keep the access code on the device instead of losing it with the tab | `api.js:13`, `:17` | **yes** |
| Poll whenever anything is waiting, not only when a batch is on screen; and say something when polling stops | `teacher.js:228-231` | **yes** |
| Build the recent-batch list from what was actually uploaded, and stop discarding a batch when the two folder-name guesses disagree | `teacher.py:92-104`, `teacher_batch.py:140-144` | no |

### (b) Things that make me distrust it or misread it

| Fix | Where | Under an hour |
|---|---|---|
| Print nothing instead of the word `null` | `teacher-screens.js:52` | **yes** |
| Stop saying "All 0 exams … are in the gradebook" for a batch that is still grading | `teacher-screens.js:44-48` | **yes** |
| Never show the browser's own error text — replace "fetch failed" with a sentence | `teacher-actions.js:21` | **yes** |
| Put the count of what needs me in the window title | `teacher.html:6`, `teacher.js` | **yes** |
| Always name the class and assessment on the held screen | `teacher-held.js:96`, `teacher-state.js:99-112` | **yes** |
| List the exams held "as a precaution" before asking me to release them | `teacher-held.js:64-87` | **yes** |
| Carry the per-criterion marks through approve and release so the exams I decided also show their detail | `teacher_batch.py` / review approval path, read by `teacher-grades.js:21-26` | no |
| Make the exams in the held lists clickable, straight into that exam | `teacher-held.js:46-49`, `teacher.js:59-67` | no |
| Add "next" and "previous" in review, that move without deciding | `teacher-review.js:200-212` | no |
| Tick "Do the same for the rest of this batch" by default, and say how many are left: "1 of 36" | `teacher-dialogs.js:68-80`, `teacher.html:60` | **yes** |
| Say the button text truthfully when more than two files are grouped ("36 separate students") | `teacher-uploading.js:41`, `:47` | **yes** |
| Do not leave a blank white page when I cancel the access code | `teacher-dialogs.js:178` | **yes** |
| Say why a student cannot be found, instead of nothing, when she is outside the 50 most recent | `teacher-screens.js:196-201`, `api.js:101-107` | **yes** |
| Show the rubric wording, not the internal criterion code, in the grade breakdown | `teacher-grades.js:6-8` | no |
| Fix the dangling "Last sent — 36 exams" when there is no time | `teacher-screens.js:61-64` | **yes** |

### (c) Polish

| Fix | Where | Under an hour |
|---|---|---|
| A pressed state on every button — there is no `transition` in the whole stylesheet | `teacher.css` | **yes** |
| Honest three-colour progress: sent / sending / could not send | `teacher.css:226-233`, `teacher-uploading.js` | no |
| A real skeleton while the scan loads, and stop fetching the same scan twice on every open | `teacher-review.js:185-234`, `teacher.js:168-202` | no |
| "Putting them in…" on the release button while it works | `teacher-actions.js:119` | **yes** |
| A finishing screen I can actually reach the next morning | `teacher-state.js:86` | **yes** |
| Show failures by student name, not by file name | `teacher-uploading.js:111-115` | **yes** |
| On a telephone, put the decisions above the scan, or make them stick to the bottom | `teacher.css:514-523` | **yes** |

---

## 6. My verdict

Would I use this every week? As it stands, no — and it is not because it is ugly or slow, it is
because on the most ordinary morning I can imagine, it loses my work and tells me it has not.
I choose a class of exams, I fill in the three boxes it asks for, and the page tells me in plain
words that I can leave and sending will carry on. Nothing is sent. Not one file. That happened to
me on the second journey I tried, and it will happen to every teacher who fills those boxes in
after choosing the files instead of before. Everything else compounds it: a full bar that counts
failures as arrivals, a page that stops refreshing without saying so, no way back to the batch I
was watching, an access code forgotten every time I close a tab, and a window that says "Nothing
needs you" while fifteen exams need me. The review screen is genuinely good — the scan beside the
marks beside the quoted line is the best thing here, and the day it releases twelve grades in one
press is the day it earns its keep. But I cannot reach a particular student without deciding on
two others first, and I have a parent on the telephone.

The single change that would most change my answer: **make sending actually start when I finish
filling in the three boxes, and never tell me I can walk away until a file is genuinely on its
way.** That is one call to `runQueue` in `teacher-upload.js:103-109` and one honest sentence in
`teacher-uploading.js:143-145`. Everything else on this list is worth doing, but until that is
fixed I would not put a class of thirty-six exams into this and go home.

*"Yo hice lo que la pantalla me dijo. Si igual se pierden, no vuelvo a usarlo."*
