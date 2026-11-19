/* ClipNova frontend: submit a YouTube URL, poll the job, render clips + SEO. */
(function () {
  "use strict";

  var form = document.getElementById("job-form");
  var urlInput = document.getElementById("url");
  var submitBtn = document.getElementById("submit-btn");
  var formError = document.getElementById("form-error");
  var videoCard = document.getElementById("video-card");
  var videoThumb = document.getElementById("video-thumb");
  var videoTitle = document.getElementById("video-title");
  var videoMeta = document.getElementById("video-meta");
  var progressCard = document.getElementById("progress-card");
  var progressMessage = document.getElementById("progress-message");
  var progressFill = document.getElementById("progress-fill");
  var progressPct = document.getElementById("progress-pct");
  var clipsSection = document.getElementById("clips-section");
  var clipsGrid = document.getElementById("clips-grid");
  var jobError = document.getElementById("job-error");

  var pollTimer = null;

  function show(el) { el.classList.remove("hidden"); }
  function hide(el) { el.classList.add("hidden"); }

  function fmtTime(sec) {
    var m = Math.floor(sec / 60);
    var s = Math.floor(sec % 60);
    return m + ":" + String(s).padStart(2, "0");
  }

  function copyText(text, btn) {
    function done() {
      var old = btn.textContent;
      btn.textContent = "Copied!";
      setTimeout(function () { btn.textContent = old; }, 1500);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, function () { fallback(); });
    } else {
      fallback();
    }
    function fallback() {
      var ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand("copy"); } catch (e) { /* ignore */ }
      document.body.removeChild(ta);
      done();
    }
  }

  function seoBlock(label, items, joiner) {
    var wrap = document.createElement("div");
    wrap.className = "seo-block";
    var h = document.createElement("h4");
    h.textContent = label;
    wrap.appendChild(h);
    var list = document.createElement("div");
    list.className = "seo-list";
    items.forEach(function (item) {
      var row = document.createElement("div");
      row.className = "seo-row";
      var span = document.createElement("span");
      span.textContent = item;
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn-copy";
      btn.textContent = "Copy";
      btn.addEventListener("click", function () { copyText(item, btn); });
      row.appendChild(span);
      row.appendChild(btn);
      list.appendChild(row);
    });
    wrap.appendChild(list);
    if (items.length > 1) {
      var all = document.createElement("button");
      all.type = "button";
      all.className = "btn-copy-all";
      all.textContent = "Copy all";
      all.addEventListener("click", function () { copyText(items.join(joiner || "\n"), all); });
      wrap.appendChild(all);
    }
    return wrap;
  }

  function clipCard(clip) {
    var card = document.createElement("article");
    card.className = "clip-card";

    var head = document.createElement("div");
    head.className = "clip-head";
    var title = document.createElement("h3");
    title.textContent = "Clip " + clip.n + " · " + fmtTime(clip.start) + "–" + fmtTime(clip.end);
    head.appendChild(title);
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
    seo.appendChild(seoBlock("Title options", clip.seo.titles, "\n"));
    seo.appendChild(seoBlock("Description", [clip.seo.description], "\n"));
    seo.appendChild(seoBlock("Hashtags", clip.seo.hashtags, " "));
    seo.appendChild(seoBlock("Tags", clip.seo.tags, ", "));
    card.appendChild(seo);

    var dl = document.createElement("a");
    dl.className = "btn-primary btn-download";
    dl.href = clip.download_url;
    dl.download = "";
    dl.textContent = "Download MP4";
    card.appendChild(dl);

    return card;
  }

  function renderJob(job) {
    if (job.title) {
      show(videoCard);
      if (job.thumbnail) {
        videoThumb.src = job.thumbnail;
        videoThumb.alt = job.title;
      }
      videoTitle.textContent = job.title;
      videoMeta.textContent = job.duration
        ? "Duration " + fmtTime(job.duration)
        : "";
    }
    progressMessage.textContent = job.message || job.status;
    progressFill.style.width = (job.progress || 0) + "%";
    progressPct.textContent = (job.progress || 0) + "%";

    if (job.status === "done") {
      hide(progressCard);
      clipsGrid.innerHTML = "";
      (job.clips || []).forEach(function (clip) {
        clipsGrid.appendChild(clipCard(clip));
      });
      show(clipsSection);
      submitBtn.disabled = false;
      submitBtn.textContent = "Cut my Shorts";
      return true;
    }
    if (job.status === "failed") {
      hide(progressCard);
      jobError.textContent = "Job failed: " + (job.error || "unknown error");
      show(jobError);
      submitBtn.disabled = false;
      submitBtn.textContent = "Cut my Shorts";
      return true;
    }
    return false;
  }

  function poll(jobId) {
    fetch("/api/jobs/" + encodeURIComponent(jobId))
      .then(function (r) {
        if (!r.ok) throw new Error("Job not found");
        return r.json();
      })
      .then(function (job) {
        if (renderJob(job)) return; // terminal state
        pollTimer = setTimeout(function () { poll(jobId); }, 2000);
      })
      .catch(function (err) {
        jobError.textContent = "Could not check job status: " + err.message;
        show(jobError);
        submitBtn.disabled = false;
        submitBtn.textContent = "Cut my Shorts";
      });
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    hide(formError);
    hide(jobError);
    hide(clipsSection);
    hide(videoCard);
    clipsGrid.innerHTML = "";
    if (pollTimer) clearTimeout(pollTimer);

    var payload = {
      url: urlInput.value.trim(),
      max_clips: parseInt(document.getElementById("max_clips").value, 10),
      clip_seconds: parseInt(document.getElementById("clip_seconds").value, 10),
    };
    submitBtn.disabled = true;
    submitBtn.textContent = "Working...";
    show(progressCard);
    progressMessage.textContent = "Starting...";
    progressFill.style.width = "0%";
    progressPct.textContent = "0%";

    fetch("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then(function (r) {
        return r.json().then(function (data) {
          if (!r.ok) throw new Error(data.detail || "Request failed");
          return data;
        });
      })
      .then(function (data) { poll(data.job_id); })
      .catch(function (err) {
        hide(progressCard);
        formError.textContent = err.message;
        show(formError);
        submitBtn.disabled = false;
        submitBtn.textContent = "Cut my Shorts";
      });
  });
})();
