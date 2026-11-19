/* ClipNova landing demo: a client-side port of the backend scoring + SEO
   rules (same lexicons, same window/score logic, simplified: no audio
   energy — neutral 10 — and no video cutting). Scores TEXT ONLY. */
(function () {
  "use strict";

  var WORD_SECONDS = 0.4; // ~150 words/minute of speech

  var POWER_WORDS = ["secret", "mistake", "free", "never", "how", "why",
    "truth", "hack", "nobody", "stop", "warning", "shocking", "insane",
    "crazy", "proven", "easy", "fast", "best", "worst", "huge", "amazing",
    "incredible", "exactly", "finally", "actually", "hidden", "real",
    "exposed", "raaz", "galti", "muft", "kabhi", "kaise", "kyu", "sach",
    "tareeka", "band", "sabse", "asli", "chhupa", "zaroor", "paise",
    "kamao", "aasan", "tez"];
  var EMOTION_WORDS = ["love", "hate", "fear", "scared", "angry", "happy",
    "sad", "cry", "laugh", "shocking", "unbelievable", "wow", "omg",
    "amazing", "incredible", "terrible", "horrible", "beautiful", "story",
    "remember", "imagine", "dream", "nightmare", "dead", "died", "killed",
    "saved", "lost", "found", "won", "failed", "success", "pain", "hurt",
    "kahani", "darr", "khushi", "dukh", "pyaar", "gussa", "sapna", "yaad",
    "maza", "dard", "jeet", "haar", "kahaani", "bhoot"];
  var QUESTION_WORDS = ["what", "why", "how", "when", "where", "who",
    "which", "did", "do", "does", "is", "are", "can", "could", "should",
    "kya", "kaise", "kyu", "kab", "kahan", "kaun"];
  var STOPWORDS = ["the", "and", "for", "with", "this", "that", "from",
    "have", "has", "are", "was", "were", "will", "would", "can", "could",
    "should", "you", "your", "they", "them", "their", "our", "its", "but",
    "not", "all", "any", "had", "her", "his", "one", "two", "about",
    "into", "than", "then", "there", "when", "what", "which", "who",
    "also", "more", "very", "just", "like", "get", "got", "going",
    "know", "think", "really", "much", "many", "some", "hai", "hain",
    "ka", "ki", "ke", "ko", "se", "mein", "me", "aur", "yeh", "woh",
    "jo", "toh", "bhi", "nahi", "kya", "tha", "thi", "kar", "karke",
    "raha", "rahi", "rahe", "aap", "hum", "is", "in", "on", "at", "to",
    "of", "a", "an", "it", "as"];

  var SAMPLES = {
    sample1: {
      title: "Money Tips",
      label: "Sample transcript — labelled sample data, not a real video.",
      text: "Did you know that most people lose money every single month without even realising it? " +
        "The secret is simple. Banks charge you hidden fees on every single transaction. " +
        "Here is the truth nobody tells you. Your savings account is actually making you poorer every year. " +
        "Inflation eats three percent of your money while the bank pays you only one percent. " +
        "So how do you stop this mistake? First, never keep all your money in one place. " +
        "Open a second account just for savings and move twenty percent of your salary there on payday. " +
        "Second, check your subscriptions right now. Most people pay for five apps they never even open. " +
        "Cancel three of them today and you will save over two thousand rupees every single month. " +
        "Third, learn the power of compound interest. If you invest just one thousand rupees every month for ten years, you will have more than two lakh rupees. " +
        "The magic is time, not timing. Start small but start today. " +
        "Remember, rich people do not work for money. They make money work for them. " +
        "The biggest mistake is waiting for the perfect moment. There is no perfect moment. " +
        "The best time to start was ten years ago. The second best time is right now. " +
        "So open your banking app and set up that automatic transfer before you forget. " +
        "Your future self will thank you for this one decision. Share this with one friend who needs to hear it."
    },
    sample2: {
      title: "Horror Story",
      label: "Sample transcript — labelled sample data, not a real video.",
      text: "Is gaon mein raat ko koi bahar nahi nikalta. Kyun? Kyunki har koi jaanta hai ki us paar wali haveli mein kuch hai. " +
        "Ek raaz jo pichhle tees saal se chhupa hua hai. Log kehte hain ki jo bhi us haveli ke andar gaya, woh kabhi wapas nahi aaya. " +
        "Ek raat, Ravi naam ka ek ladka apne doston ke saath shart lagata hai. Main haveli ke andar jaakar ek ghanta bitaunga, woh kehta hai. " +
        "Uske dost haste hain. Lekin Ravi sach mein chala jaata hai. Darwaza khulte hi ek thandi hawa uske chehre se takraati hai. " +
        "Andar andhera itna gehra hai ki haath bhi nahi dikhta. Phir achanak, ek awaaz aati hai. Koi uska naam pukaar raha hai. Ravi... Ravi... " +
        "Uske dil ki dhadkan tez ho jaati hai. Woh peeche mudta hai, lekin wahan koi nahi hota. " +
        "Tabhi, upar ke kamre se ek bachche ke rone ki awaaz aati hai. Ravi ki saansein ruk jaati hain. " +
        "Us haveli mein tees saal se koi bachcha nahi rehta. Phir yeh awaaz kahan se aa rahi hai? " +
        "Woh seedhiyon ki taraf badhta hai. Har kadam par lakdi ki cheekh goonjti hai. " +
        "Aur phir, uski aankhon ke saamne jo hota hai, woh aap soch bhi nahi sakte. " +
        "Ek parchhai, ek chehra, aur ek sach jo us gaon ko hamesha ke liye badal dega. " +
        "Agli subah jab gaon wale haveli pahunche, darwaza khula tha. Andar sirf ek cheez mili. Ravi ki ghadi, jo raat ke exactly teen baje ruk gayi thi. " +
        "Aaj bhi, har poornima ki raat, us haveli se ek awaaz aati hai. Koi kehta hai, Ravi wapas aa gaya. Koi kehta hai, woh kabhi gaya hi nahi."
    }
  };

  function clean(w) {
    return w.toLowerCase().replace(/[^a-z0-9\u0900-\u097f]/g, "");
  }

  function wordsFromText(text) {
    var raw = text.split(/\s+/).filter(Boolean);
    return raw.map(function (w, i) {
      return { word: w, start: i * WORD_SECONDS, end: (i + 1) * WORD_SECONDS };
    });
  }

  function sentenceSpans(words) {
    var spans = [];
    var start = 0;
    for (var i = 0; i < words.length; i++) {
      if (/[.!?…]+$/.test(words[i].word.trim()) || i - start >= 40) {
        spans.push([start, i + 1]);
        start = i + 1;
      }
    }
    if (start < words.length) spans.push([start, words.length]);
    return spans;
  }

  function buildWindows(words, clipSeconds) {
    var spans = sentenceSpans(words);
    var windows = [];
    var i = 0;
    var totalEnd = words[words.length - 1].end;
    while (i < spans.length) {
      var startIdx = spans[i][0];
      var startT = words[startIdx].start;
      var j = i;
      var endT = words[spans[j][1] - 1].end;
      while (j + 1 < spans.length && endT - startT < clipSeconds) {
        var nextEnd = words[spans[j + 1][1] - 1].end;
        if (nextEnd - startT > 60) break;
        j += 1;
        endT = nextEnd;
      }
      if (endT - startT >= 30) {
        var endIdx = spans[j][1];
        windows.push({
          start: startT, end: endT, startIdx: startIdx, endIdx: endIdx,
          text: words.slice(startIdx, endIdx).map(function (w) { return w.word; }).join(" ")
        });
      }
      var target = startT + 15;
      var next = i + 1;
      while (next < spans.length && words[spans[next][0]].start < target) next += 1;
      i = Math.max(next, i + 1);
      if (i < spans.length && totalEnd - words[spans[i][0]].start < 30) break;
    }
    return windows;
  }

  function scoreWindow(win, words, title) {
    var wWords = words.slice(win.startIdx, win.endIdx);
    var t0 = wWords[0].start;
    var first = wWords.filter(function (w) { return w.start - t0 <= 5; });
    if (!first.length) first = wWords.slice(0, 8);
    var firstText = first.map(function (w) { return w.word; }).join(" ");
    var firstClean = first.map(function (w) { return clean(w.word); });
    var hook = 0;
    if (firstText.indexOf("?") !== -1) hook += 10;
    if (/\d/.test(firstText)) hook += 6;
    var power = firstClean.filter(function (c) { return POWER_WORDS.indexOf(c) !== -1; }).length;
    hook += Math.min(12, power * 4);
    if (firstClean.length && QUESTION_WORDS.indexOf(firstClean[0]) !== -1) hook += 2;
    hook = Math.min(30, hook);

    var overlap = 0;
    if (title) {
      var titleWords = title.split(/\s+/).map(clean)
        .filter(function (w) { return w.length > 2 && STOPWORDS.indexOf(w) === -1; });
      if (titleWords.length) {
        var textSet = {};
        win.text.split(/\s+/).forEach(function (w) { textSet[clean(w)] = true; });
        var hits = titleWords.filter(function (w) { return textSet[w]; }).length;
        overlap = 20 * hits / titleWords.length;
      }
    }

    var emotion = 0;
    win.text.split(/\s+/).forEach(function (w) {
      if (EMOTION_WORDS.indexOf(clean(w)) !== -1) emotion += 1;
    });
    emotion = Math.min(15, emotion * 3);

    var energy = 10; // neutral: the text-only demo has no audio
    var complete = 15;
    var total = Math.min(100, hook + overlap + energy + complete + emotion);

    var parts = [];
    if (hook >= 14) parts.push("Strong hook");
    else if (hook >= 8) parts.push("Good hook");
    if (overlap >= 12) parts.push("matches title");
    if (emotion >= 9) parts.push("emotional peak");
    if (!parts.length) parts.push("complete story beat");
    return { score: Math.round(total * 10) / 10, reason: parts.join(" + ") };
  }

  function overlapRatio(a, b) {
    var overlap = Math.max(0, Math.min(a.end, b.end) - Math.max(a.start, b.start));
    var shorter = Math.min(a.end - a.start, b.end - b.start);
    return shorter > 0 ? overlap / shorter : 0;
  }

  function rankClips(words, title) {
    var scored = buildWindows(words, 45).map(function (win) {
      var s = scoreWindow(win, words, title);
      return {
        start: Math.round(win.start * 100) / 100,
        end: Math.round(win.end * 100) / 100,
        duration: Math.round((win.end - win.start) * 10) / 10,
        score: s.score, reason: s.reason, text: win.text
      };
    });
    scored.sort(function (a, b) { return b.score - a.score; });
    var picked = [];
    for (var i = 0; i < scored.length && picked.length < 3; i++) {
      var cand = scored[i];
      var dup = picked.some(function (p) { return overlapRatio(cand, p) > 0.3; });
      if (!dup) picked.push(cand);
    }
    return picked;
  }

  function extractKeywords(text, title) {
    var freq = {};
    var titleSet = {};
    (title || "").toLowerCase().split(/[^a-z\u0900-\u097f]+/).forEach(function (w) {
      if (w.length >= 3) titleSet[w] = true;
    });
    text.toLowerCase().split(/[^a-z\u0900-\u097f]+/).forEach(function (w) {
      if (w.length < 3 || STOPWORDS.indexOf(w) !== -1) return;
      freq[w] = (freq[w] || 0) + 1;
    });
    Object.keys(titleSet).forEach(function (w) {
      if (freq[w]) freq[w] += 3;
    });
    return Object.keys(freq).sort(function (a, b) { return freq[b] - freq[a]; }).slice(0, 12);
  }

  function seoTitles(keywords, clipText) {
    var kw = keywords[0] || "this";
    var kw2 = keywords[1] || kw;
    var n = 3 + (clipText.length % 3);
    var curiosity = [
      "The " + kw + " Secret Nobody Tells You",
      "Nobody Talks About This " + kw + " Truth",
      "This " + kw + " Fact Will Surprise You",
      "The Hidden Truth About " + kw,
      "Why Everyone Is Wrong About " + kw
    ];
    var howto = [
      "How to Master " + kw2 + " in 60 Seconds",
      n + " " + kw2 + " Mistakes You Must Avoid",
      "How " + kw2 + " Actually Works (Explained Fast)",
      n + " " + kw2 + " Tips That Actually Work",
      "Stop Doing " + kw2 + " Wrong — Do This Instead"
    ];
    var keywordLed = [
      kw.charAt(0).toUpperCase() + kw.slice(1) + " Explained in 60 Seconds",
      kw.charAt(0).toUpperCase() + kw.slice(1) + ": What You Need to Know",
      kw.charAt(0).toUpperCase() + kw.slice(1) + " — The Full Story in One Minute",
      "Everything About " + kw.charAt(0).toUpperCase() + kw.slice(1) + ", Fast"
    ];
    return [
      curiosity[kw.length % curiosity.length],
      howto[kw2.length % howto.length],
      keywordLed[kw.length % keywordLed.length]
    ];
  }

  function fmtTime(sec) {
    var m = Math.floor(sec / 60);
    var s = Math.floor(sec % 60);
    return m + ":" + String(s).padStart(2, "0");
  }

  // ---- UI wiring ----
  var select = document.getElementById("sample-select");
  var textarea = document.getElementById("transcript-input");
  var sampleLabel = document.getElementById("sample-label");
  var runBtn = document.getElementById("demo-run");
  var errorEl = document.getElementById("demo-error");
  var resultsEl = document.getElementById("demo-results");

  function currentSample() {
    return SAMPLES[select.value] || null;
  }

  function refreshInput() {
    var sample = currentSample();
    if (sample) {
      textarea.value = sample.text;
      textarea.readOnly = true;
      sampleLabel.textContent = sample.label;
      sampleLabel.classList.remove("hidden");
    } else {
      textarea.value = "";
      textarea.readOnly = false;
      textarea.focus();
      sampleLabel.classList.add("hidden");
    }
    resultsEl.innerHTML = "";
    errorEl.classList.add("hidden");
  }

  select.addEventListener("change", refreshInput);

  runBtn.addEventListener("click", function () {
    var text = textarea.value.trim();
    var sample = currentSample();
    var title = sample ? sample.title : "";
    errorEl.classList.add("hidden");
    resultsEl.innerHTML = "";
    if (text.split(/\s+/).length < 75) {
      errorEl.textContent = "Paste at least ~75 words (about 30 seconds of speech) to score.";
      errorEl.classList.remove("hidden");
      return;
    }
    var words = wordsFromText(text);
    var clips = rankClips(words, title);
    if (!clips.length) {
      errorEl.textContent = "Not enough speech to form a 30-second clip. Paste a longer transcript.";
      errorEl.classList.remove("hidden");
      return;
    }
    clips.forEach(function (clip, idx) {
      var keywords = extractKeywords(clip.text, title);
      var titles = seoTitles(keywords, clip.text);
      var card = document.createElement("article");
      card.className = "clip-card";

      var head = document.createElement("div");
      head.className = "clip-head";
      var h = document.createElement("h3");
      h.textContent = "Clip " + (idx + 1) + " · " + fmtTime(clip.start) + "–" + fmtTime(clip.end);
      head.appendChild(h);
      var score = document.createElement("span");
      score.className = "clip-score";
      score.textContent = "Score " + clip.score + "/100";
      head.appendChild(score);
      card.appendChild(head);

      var bar = document.createElement("div");
      bar.className = "score-bar";
      var fill = document.createElement("div");
      fill.className = "score-fill";
      fill.style.width = Math.max(0, Math.min(100, clip.score)) + "%";
      bar.appendChild(fill);
      card.appendChild(bar);

      var reason = document.createElement("p");
      reason.className = "clip-reason";
      reason.textContent = clip.reason;
      card.appendChild(reason);

      var quote = document.createElement("blockquote");
      quote.className = "clip-text";
      quote.textContent = "“" + clip.text.slice(0, 220) + (clip.text.length > 220 ? "…" : "") + "”";
      card.appendChild(quote);

      var seo = document.createElement("div");
      seo.className = "seo-panel";
      var sh = document.createElement("h4");
      sh.textContent = "Title options";
      seo.appendChild(sh);
      titles.forEach(function (t) {
        var row = document.createElement("div");
        row.className = "seo-row";
        var span = document.createElement("span");
        span.textContent = t;
        row.appendChild(span);
        seo.appendChild(row);
      });
      card.appendChild(seo);

      var note = document.createElement("p");
      note.className = "muted demo-card-note";
      note.textContent = "In the full app this clip is cut as a vertical MP4 with captions + a full SEO pack.";
      card.appendChild(note);

      resultsEl.appendChild(card);
    });
  });

  refreshInput();
})();
