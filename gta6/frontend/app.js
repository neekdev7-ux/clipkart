/* ClipNova GTA 6 Edition dashboard: monitor control, live streams,
   detected clip queue (approve/reject/upload), upload log — plus the
   original cut-any-video job flow. */
(function () {
  "use strict";

  /* ---------- shared helpers ---------- */

  function show(el) { el.classList.remove("hidden"); }
  function hide(el) { el.classList.add("hidden"); }

  function fmtTime(sec) {
    var m = Math.floor(sec / 60);
    var s = Math.floor(sec % 60);
    return m + ":" + String(s).padStart(2, "0");
  }

  function fmtBytes(bytes) {
    if (!bytes) return "0 MB";
    if (bytes < 1024 * 1024) return Math.round(bytes / 1024) + " KB";
    if (bytes < 1024 * 1024 * 1024) return (bytes / 1024 / 1024).toFixed(1) + " MB";
    return (bytes / 1024 / 1024 / 1024).toFixed(2) + " GB";
  }

  function fmtViewers(n) {
    if (!n) return "–";
    if (n >= 1000) return (n / 1000).toFixed(1) + "k";
    return String(n);
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

  /* ---------- monitor + status ---------- */

  var modePill = document.getElementById("mode-pill");
  var monitorStatus = document.getElementById("monitor-status");
  var monitorStart = document.getElementById("monitor-start");
  var monitorStop = document.getElementById("monitor-stop");
  var quotaText = document.getElementById("quota-text");
  var quotaFill = document.getElementById("quota-fill");
  var youtubeAuth = document.getElementById("youtube-auth");
  var statTiles = document.getElementById("stat-tiles");

  function statTile(label, value) {
    var tile = document.createElement("div");
    tile.className = "stat-tile";
    var l = document.createElement("div");
    l.className = "stat-label";
    l.textContent = label;
    var v = document.createElement("div");
    v.className = "stat-value";
    v.textContent = value;
    tile.appendChild(l);
    tile.appendChild(v);
    return tile;
  }

  function renderStatus(s) {
    modePill.textContent = s.youtube && s.youtube.auto_upload
      ? "Auto-upload ON" : "Dry-run mode";
    monitorStatus.textContent = s.running
      ? "Monitor is running — watching GTA 6 live streams."
      : "Monitor is stopped.";
    monitorStatus.classList.toggle("live", !!s.running);
    monitorStart.disabled = !!s.running;
    monitorStop.disabled = !s.running;

    var q = s.quota || {};
    quotaText.textContent = (q.uploads_today || 0) + " / " +
      (q.max_uploads_per_day || 6) + " uploads · " +
      (q.quota_units_used || 0) + " / " + (q.quota_units_daily || 10000) + " units";
    quotaFill.style.width = Math.min(100,
      100 * (q.quota_units_used || 0) / (q.quota_units_daily || 10000)) + "%";

    var yt = s.youtube || {};
    if (yt.authorized) {
      youtubeAuth.textContent = "YouTube: connected — uploads ready.";
    } else if (yt.configured) {
      youtubeAuth.innerHTML = "YouTube: not connected — <a href=\"/auth/youtube\">Connect channel</a>";
    } else {
      youtubeAuth.textContent = "YouTube: not configured — set YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET in .env (see README).";
    }

    statTiles.innerHTML = "";
    var st = s.stats || {};
    statTiles.appendChild(statTile("Streams found", st.discovered || 0));
    statTiles.appendChild(statTile("Streams recorded", st.recorded || 0));
    statTiles.appendChild(statTile("Clips cut", st.clips || 0));
    statTiles.appendChild(statTile("Uploaded", st.uploaded || 0));
    statTiles.appendChild(statTile("Disk used", fmtBytes(s.disk_bytes) +
      " / " + fmtBytes(s.disk_cap_bytes)));
    statTiles.appendChild(statTile("Watched now", (s.watched || []).length));
  }

  monitorStart.addEventListener("click", function () {
    fetch("/api/monitor/start", { method: "POST" }).then(refreshAll);
  });
  monitorStop.addEventListener("click", function () {
    fetch("/api/monitor/stop", { method: "POST" }).then(refreshAll);
  });

  /* ---------- streams ---------- */

  var streamsList = document.getElementById("streams-list");
  var watchForm = document.getElementById("watch-form");
  var watchInput = document.getElementById("watch-input");
  var watchError = document.getElementById("watch-error");

  function streamRow(s) {
    var row = document.createElement("div");
    row.className = "stream-row";
    var info = document.createElement("div");
    info.className = "stream-info";
    var title = document.createElement("a");
    title.href = s.url;
    title.target = "_blank";
    title.rel = "noopener";
    title.textContent = s.title || s.video_id;
    info.appendChild(title);
    var meta = document.createElement("div");
    meta.className = "stream-meta";
    meta.textContent = (s.channel || "Unknown channel") + " · " +
      fmtViewers(s.viewers) + " watching";
    info.appendChild(meta);
    row.appendChild(info);

    var pill = document.createElement("span");
    pill.className = "status-pill status-" + s.status;
    pill.textContent = s.status;
    row.appendChild(pill);

    var rm = document.createElement("button");
    rm.type = "button";
    rm.className = "btn-copy";
    rm.textContent = "Remove";
    rm.addEventListener("click", function () {
      fetch("/api/streams/" + encodeURIComponent(s.id), { method: "DELETE" })
        .then(refreshAll);
    });
    row.appendChild(rm);
    return row;
  }

  function renderStreams(data) {
    var streams = data.streams || [];
    streamsList.innerHTML = "";
    if (!streams.length) {
      var p = document.createElement("p");
      p.className = "muted";
      p.textContent = "No streams on the watchlist yet.";
      streamsList.appendChild(p);
      return;
    }
    streams.forEach(function (s) { streamsList.appendChild(streamRow(s)); });
  }

  watchForm.addEventListener("submit", function (e) {
    e.preventDefault();
    hide(watchError);
    var value = watchInput.value.trim();
    if (!value) return;
    var payload = value.indexOf("http") === 0 ? { url: value } : { query: value };
    fetch("/api/streams/watch", {
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
      .then(function () {
        watchInput.value = "";
        refreshAll();
      })
      .catch(function (err) {
        watchError.textContent = err.message;
        show(watchError);
      });
  });

  /* ---------- clip queue ---------- */

  var clipsGrid = document.getElementById("clips-grid");
  var clipsEmpty = document.getElementById("clips-empty");
  var clipFilter = "";

  document.querySelectorAll(".btn-filter").forEach(function (btn) {
    btn.addEventListener("click", function () {
      document.querySelectorAll(".btn-filter").forEach(function (b) {
        b.classList.remove("active");
      });
      btn.classList.add("active");
      clipFilter = btn.getAttribute("data-filter") || "";
      refreshClips();
    });
  });

  function clipCard(clip) {
    var card = document.createElement("article");
    card.className = "clip-card";

    var head = document.createElement("div");
    head.className = "clip-head";
    var title = document.createElement("h3");
    title.textContent = fmtTime(clip.start) + "–" + fmtTime(clip.end) +
      " · " + Math.round(clip.duration) + "s";
    head.appendChild(title);
    var score = document.createElement("span");
    score.className = "clip-score";
    score.textContent = "Score " + clip.score + "/100";
    head.appendChild(score);
    card.appendChild(head);

    var status = document.createElement("span");
    status.className = "status-pill status-" + clip.status;
    status.textContent = clip.status;
    card.appendChild(status);

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

    var source = document.createElement("p");
    source.className = "clip-source muted";
    source.textContent = "From: " + (clip.stream_title || "live stream") +
      (clip.channel ? " by " + clip.channel : "");
    card.appendChild(source);

    var quote = document.createElement("blockquote");
    quote.className = "clip-text";
    quote.textContent = "“" + (clip.text || "").slice(0, 220) +
      ((clip.text || "").length > 220 ? "…" : "") + "”";
    card.appendChild(quote);

    var seo = clip.seo || {};
    var seoWrap = document.createElement("div");
    seoWrap.className = "seo-panel";
    if (seo.titles) seoWrap.appendChild(seoBlock("Title options", seo.titles, "\n"));
    if (seo.description) seoWrap.appendChild(seoBlock("Description", [seo.description], "\n"));
    if (seo.hashtags) seoWrap.appendChild(seoBlock("Hashtags", seo.hashtags, " "));
    if (seo.tags) seoWrap.appendChild(seoBlock("Tags", seo.tags, ", "));
    card.appendChild(seoWrap);

    var actions = document.createElement("div");
    actions.className = "clip-actions";

    function actionBtn(label, cls, fn) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = cls;
      b.textContent = label;
      b.addEventListener("click", fn);
      actions.appendChild(b);
      return b;
    }

    if (clip.status === "detected" || clip.status === "approved") {
      if (clip.status === "detected") {
        actionBtn("Approve", "btn-primary btn-small", function () {
          fetch("/api/clips/" + clip.id + "/approve", { method: "POST" })
            .then(refreshAll);
        });
        actionBtn("Reject", "btn-secondary btn-small", function () {
          fetch("/api/clips/" + clip.id + "/reject", { method: "POST" })
            .then(refreshAll);
        });
      }
      actionBtn("Upload to YouTube", "btn-primary btn-small", function () {
        var btn = this;
        btn.disabled = true;
        btn.textContent = "Uploading...";
        fetch("/api/clips/" + clip.id + "/upload", { method: "POST" })
          .then(function (r) { return r.json(); })
          .then(function (data) {
            if (data.dry_run) {
              alert("Dry-run: upload simulated, nothing sent to YouTube.\n" +
                "Enable AUTO_UPLOAD + connect your channel to go live.");
            } else if (data.url) {
              alert("Uploaded! " + data.url);
            } else if (data.detail) {
              alert("Upload blocked: " + data.detail);
            }
            refreshAll();
          })
          .catch(function () {
            btn.disabled = false;
            btn.textContent = "Upload to YouTube";
          });
      });
    }
    if (clip.youtube_video_id) {
      var ytLink = document.createElement("a");
      ytLink.className = "btn-secondary btn-small";
      ytLink.href = "https://www.youtube.com/shorts/" + clip.youtube_video_id;
      ytLink.target = "_blank";
      ytLink.rel = "noopener";
      ytLink.textContent = "Watch on YouTube";
      actions.appendChild(ytLink);
    }

    var dl = document.createElement("a");
    dl.className = "btn-secondary btn-small";
    dl.href = "/api/clips/" + clip.id + "/download";
    dl.download = "";
    dl.textContent = "Download MP4";
    actions.appendChild(dl);

    card.appendChild(actions);
    return card;
  }

  function renderClips(data) {
    var clips = data.clips || [];
    clipsGrid.innerHTML = "";
    if (!clips.length) {
      show(clipsEmpty);
      return;
    }
    hide(clipsEmpty);
    clips.forEach(function (clip) { clipsGrid.appendChild(clipCard(clip)); });
  }

  /* ---------- upload log ---------- */

  var uploadsList = document.getElementById("uploads-list");

  function renderUploads(data) {
    var uploads = data.uploads || [];
    uploadsList.innerHTML = "";
    if (!uploads.length) {
      var p = document.createElement("p");
      p.className = "muted";
      p.textContent = "No upload attempts yet.";
      uploadsList.appendChild(p);
      return;
    }
    uploads.slice(0, 10).forEach(function (u) {
      var row = document.createElement("div");
      row.className = "upload-row";
      var left = document.createElement("span");
      left.className = "mono";
      left.textContent = (u.created_at || "") + " · clip " +
        (u.clip_id || "").slice(0, 8);
      var pill = document.createElement("span");
      pill.className = "status-pill status-" + u.status;
      pill.textContent = u.status + (u.dry_run ? " (dry-run)" : "");
      var right = document.createElement("span");
      right.className = "muted";
      right.textContent = u.youtube_video_id
        ? "youtube.com/shorts/" + u.youtube_video_id
        : (u.error || "");
      row.appendChild(left);
      row.appendChild(pill);
      row.appendChild(right);
      uploadsList.appendChild(row);
    });
  }

  /* ---------- refresh loop ---------- */

  function refreshStatus() {
    return fetch("/api/status").then(function (r) { return r.json(); })
      .then(renderStatus).catch(function () { /* keep old state */ });
  }

  function refreshStreams() {
    return fetch("/api/streams").then(function (r) { return r.json(); })
      .then(renderStreams).catch(function () { /* keep old state */ });
  }

  function refreshClips() {
    var url = "/api/clips" + (clipFilter ? "?status=" + clipFilter : "");
    return fetch(url).then(function (r) { return r.json(); })
      .then(renderClips).catch(function () { /* keep old state */ });
  }

  function refreshQueue() {
    return fetch("/api/queue").then(function (r) { return r.json(); })
      .then(renderUploads).catch(function () { /* keep old state */ });
  }

  function refreshAll() {
    refreshStatus();
    refreshStreams();
    refreshClips();
    refreshQueue();
  }

  refreshAll();
  setInterval(refreshAll, 10000);

  /* ---------- original job flow (cut any video) ---------- */

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
  var jobClipsSection = document.getElementById("job-clips-section");
  var jobClipsGrid = document.getElementById("job-clips-grid");
  var jobError = document.getElementById("job-error");

  var pollTimer = null;

  function jobClipCard(clip) {
    var card = document.createElement("article");
    card.className = "clip-card";
    var head = document.createElement("div");
    head.className = "clip-head";
    var title = document.createElement("h3");
    title.textContent = "Clip " + clip.n + " · " + fmtTime(clip.start) +
      "–" + fmtTime(clip.end);
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
    quote.textContent = "“" + clip.text.slice(0, 220) +
      (clip.text.length > 220 ? "…" : "") + "”";
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
      jobClipsGrid.innerHTML = "";
      (job.clips || []).forEach(function (clip) {
        jobClipsGrid.appendChild(jobClipCard(clip));
      });
      show(jobClipsSection);
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
        if (renderJob(job)) return;
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
    hide(jobClipsSection);
    hide(videoCard);
    jobClipsGrid.innerHTML = "";
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
