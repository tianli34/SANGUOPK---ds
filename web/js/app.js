/*
 * 文件名: app.js
 * 用途: 网页入口 —— 加载战斗事件、同步面板与战报、控制播放与回退
 *
 * 所有 HP / SP / 胆气 / 伤害均来自事件 JSON 的状态快照与差值，
 * 前端不做任何命中或伤害计算。
 */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const esc = (value) =>
    String(value === null || value === undefined ? "" : value).replace(/[&<>"']/g, (ch) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[ch]));

  const TIER_CLASSES = ["tier-0", "tier-1", "tier-2", "tier-3"];

  // file:// 直接打开时没有同源后端，尝试连接默认端口的本地服务
  const API_BASE =
    window.location.protocol === "file:" ? "http://127.0.0.1:8000/" : "";

  const S = {
    doc: null,
    events: [],
    warriors: null,
    initial: null,
    cursor: -1,
    playing: false,
    paused: false,
    speed: 1,
    token: 0,
    log: null,
    scene: null,
    lastRound: null,
  };

  const els = {
    stage: $("stage"),
    roundLabel: $("round-label"),
    tickLabel: $("tick-label"),
    actionRound: $("action-round"),
    actionText: $("action-text"),
    hpLead: $("hp-lead"),
    spLead: $("sp-lead"),
    progress: $("progress"),
    eventCounter: $("event-counter"),
    logList: $("log-list"),
    logNote: $("log-note"),
    logPanel: $("log-panel"),
    leadReport: $("lead-report"),
    leadReportGrid: $("lead-report-grid"),
    resultOverlay: $("result-overlay"),
    resultTitle: $("result-title"),
    resultSub: $("result-sub"),
    resultStats: $("result-stats"),
    emptyState: $("empty-state"),
    btnPlay: $("btn-play"),
    btnNew: $("btn-new"),
    btnLive: $("btn-live"),
    btnPrev: $("btn-prev"),
    btnReplay: $("btn-replay"),
    btnEnd: $("btn-end"),
    btnResultNew: $("btn-result-new"),
    setupOverlay: $("setup-overlay"),
    setupError: $("setup-error"),
    btnSetupStart: $("btn-setup-start"),
    progressHint: $("progress-hint"),
    liveHint: $("live-hint"),
  };

  /* ================= 顶部状态面板 ================= */

  const Hud = {
    init(doc) {
      this.doc = doc;
      this.warriors = doc.warriors;
      this.prevTier = { A: { hp: null, sp: null }, B: { hp: null, sp: null } };
      if (this.courageTimers) {
        ["A", "B"].forEach((side) => window.clearTimeout(this.courageTimers[side]));
      }
      this.courageTimers = { A: null, B: null };
      this.leaderText = { hp: null, sp: null };

      ["A", "B"].forEach((side) => {
        const caption = $("courage-caption-" + side);
        caption.textContent = "";
        caption.classList.remove("is-up", "is-down");
      });

      ["A", "B"].forEach((side) => {
        const warrior = doc.warriors[side];
        $("name-" + side).textContent = warrior.name;
        const skillEl = $("skill-" + side);
        const skillInfos =
          warrior.skillInfo && warrior.skillInfo.length
            ? warrior.skillInfo
            : (warrior.skills || []).map((text) => ({
                name: text.split("（")[0],
                description: text,
                enabled: true,
              }));
        if (skillInfos.length) {
          skillEl.textContent = `特技 · ${skillInfos
            .map((info) => (info.enabled === false ? `${info.name}(关闭)` : info.name))
            .join(" / ")}`;
          skillEl.title = skillInfos
            .map(
              (info) =>
                `${info.category ? `[${info.category}] ` : ""}${info.name}：${
                  info.description || ""
                }`
            )
            .join("\n");
          skillEl.hidden = false;
        } else {
          skillEl.hidden = true;
        }

        const weaponEl = $("weapon-" + side);
        const weapon = warrior.weapon;
        if (weapon && weapon.name) {
          weaponEl.textContent = `兵器 · ${weapon.name}`;
          weaponEl.title = weapon.reach
            ? `${weapon.categoryLabel || ""} · 射程 ${weapon.reach} 格`
            : weapon.categoryLabel || "";
          weaponEl.hidden = false;
        } else {
          weaponEl.hidden = true;
        }
      });

      this.apply(initialState(doc), { instant: true });
    },

    apply(state, options = {}) {
      const instant = Boolean(options.instant);
      const effects = options.effects || null;
      const flash = !instant && options.flash !== false;

      ["A", "B"].forEach((side) => {
        const warrior = this.warriors[side];
        const current = state[side];
        const hpPct = clamp(current.hp / warrior.hpMax, 0, 1);
        const spPct = clamp(current.sp / warrior.spMax, 0, 1);

        this.setGauge(side, "hp", current.hp, warrior.hpMax, hpPct, flash);
        this.setGauge(side, "sp", current.sp, warrior.spMax, spPct, flash);

        $("courage-" + side).textContent = String(current.courage);

        if (effects && effects[side]) {
          const delta = effects[side].courage;
          if (delta && Math.abs(delta) >= 10) this.showCourageTip(side, delta);
        }
      });

      this.renderLeaders(state, !instant);
    },

    setGauge(side, stat, value, max, pct, flash) {
      const gauge = $(`${stat}-gauge-${side}`);
      const fill = gauge.querySelector(".gauge-fill");
      const valueEl = $(`${stat}-value-${side}`);
      const label = stat === "hp" ? "HP" : "SP";

      fill.style.width = `${(pct * 100).toFixed(2)}%`;
      valueEl.textContent = String(Math.round(value));
      gauge.title = `${label} ${Math.round(value)} / ${Math.round(max)}（${(pct * 100).toFixed(1)}%）`;

      const tier = pct >= 0.75 ? 0 : pct >= 0.5 ? 1 : pct >= 0.25 ? 2 : 3;
      gauge.classList.remove(...TIER_CLASSES);
      gauge.classList.add(`tier-${tier}`);

      const prev = this.prevTier[side][stat];
      if (flash && prev !== null && tier > prev) {
        const track = gauge.querySelector(".gauge-track");
        const seq = (gauge._flashSeq = (gauge._flashSeq || 0) + 1);
        gauge.classList.remove("tier-flash");
        void gauge.offsetWidth;
        gauge.classList.add("tier-flash");
        const clear = (event) => {
          if (event.target !== track || event.animationName !== "tier-flash") return;
          gauge.removeEventListener("animationend", clear);
          if (gauge._flashSeq === seq) gauge.classList.remove("tier-flash");
        };
        gauge.addEventListener("animationend", clear);
      }
      this.prevTier[side][stat] = tier;
    },

    showCourageTip(side, delta) {
      const el = $("courage-caption-" + side);
      el.textContent = `胆气 ${delta > 0 ? "+" : ""}${delta}`;
      el.classList.remove("is-up", "is-down");
      el.classList.add(delta > 0 ? "is-up" : "is-down");
      window.clearTimeout(this.courageTimers[side]);
      this.courageTimers[side] = window.setTimeout(() => {
        el.classList.remove("is-up", "is-down");
      }, 1400);
    },

    renderLeaders(state, animate) {
      const a = this.warriors.A;
      const b = this.warriors.B;
      const hpA = (state.A.hp / a.hpMax) * 100;
      const hpB = (state.B.hp / b.hpMax) * 100;
      const spA = (state.A.sp / a.spMax) * 100;
      const spB = (state.B.sp / b.spMax) * 100;

      const lines = {
        hp: leaderLine("HP", a.name, hpA, b.name, hpB),
        sp: leaderLine("SP", a.name, spA, b.name, spB),
      };

      [["hp", els.hpLead], ["sp", els.spLead]].forEach(([key, el]) => {
        if (this.leaderText[key] === lines[key].html) return;
        const previous = this.leaderText[key];
        this.leaderText[key] = lines[key].html;
        el.innerHTML = lines[key].html;
        if (animate && previous !== null) {
          el.classList.remove("lead-changed");
          void el.offsetWidth;
          el.classList.add("lead-changed");
        }
      });
    },
  };

  function leaderLine(label, nameA, pctA, nameB, pctB) {
    const diff = pctA - pctB;
    if (Math.abs(diff) < 0.0001) {
      return {
        html: `${label} 持平 <span class="lead-pct">（${nameA} ${pctA.toFixed(1)}% / ${nameB} ${pctB.toFixed(1)}%）</span>`,
      };
    }
    const leader = diff > 0 ? nameA : nameB;
    const gap = Math.abs(diff).toFixed(1);
    return {
      html: `${label} 领先 · <b>${esc(leader)}</b> +${gap} 个百分点 <span class="lead-pct">（${nameA} ${pctA.toFixed(1)}% / ${nameB} ${pctB.toFixed(1)}%）</span>`,
    };
  }

  function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
  }

  function initialState(doc) {
    const make = (side) => {
      const warrior = doc.warriors[side];
      const state = {
        name: warrior.name,
        hp: warrior.hp,
        sp: warrior.sp,
        courage: warrior.courage,
        alive: true,
      };
      if (doc.map) state.position = doc.map.spawns[side];
      return state;
    };
    return { A: make("A"), B: make("B") };
  }

  function renderLeadReport(doc) {
    const records = doc.battle && doc.battle.leadRecords;
    if (!records) return;
    const names = { A: doc.warriors.A.name, B: doc.warriors.B.name };

    els.leadReportGrid.innerHTML = ["hp", "sp"].map((key) => {
      const section = records[key];
      if (!section) return "";
      const rows = (section.changes || [])
        .map((change) => {
          const name = change.name || names[change.side] || "";
          return `<tr><td>第 ${esc(change.round)} 回合</td><td>${esc(name)}领先</td></tr>`;
        })
        .join("");
      const longest = section.longest || { A: 0, B: 0 };
      const maxGap = section.maxGap || { A: 0, B: 0 };
      return `<section class="lead-col">
        <h4>${key.toUpperCase()}</h4>
        ${rows ? `<table class="lead-table"><tbody>${rows}</tbody></table>` : `<p class="lead-empty">全程持平</p>`}
        <ul class="lead-metrics">
          <li>最长持续领先：<b>${esc(names.A)}</b> ${longest.A} 回合 · <b>${esc(names.B)}</b> ${longest.B} 回合</li>
          <li>最大领先幅度：<b>${esc(names.A)}</b> ${(maxGap.A * 100).toFixed(1)}% · <b>${esc(names.B)}</b> ${(maxGap.B * 100).toFixed(1)}%</li>
        </ul>
      </section>`;
    }).join("");
  }

  function showLeadReport(visible) {
    if (!els.leadReport) return;
    els.leadReport.hidden = !visible || !els.leadReportGrid.innerHTML;
  }

  /* ================= 战报 ================= */

  class LogView {
    constructor() {
      this.list = els.logList;
      this.note = els.logNote;
      this.logged = -1;
      this.round = 0;
      this.currentEl = null;
      this.total = 0;
    }

    clear() {
      this.list.innerHTML = "";
      this.logged = -1;
      this.round = 0;
      this.currentEl = null;
      this.note.textContent = "按事件回放 · 可前后拖动";
    }

    rebuild(events, upto, total) {
      this.total = total;
      this.clear();
      for (let i = 0; i <= upto; i += 1) {
        this.add(events[i], i, true);
      }
      this.scrollToEnd();
    }

    ensureRound(ev) {
      if (!ev.round || ev.round === this.round) return;
      this.round = ev.round;
      const head = document.createElement("li");
      head.className = "log-round-head";
      head.textContent = `第 ${ev.round} 回合`;
      this.list.appendChild(head);
    }

    add(ev, index, silent) {
      if (index <= this.logged) return;
      this.ensureRound(ev);
      this.logged = index;

      if (ev.type === "round_end") return;

      const li = document.createElement("li");
      li.dataset.index = String(index);

      if (ev.type === "battle_start") {
        li.className = "log-entry is-start";
        li.innerHTML = "战鼓擂响，两将出阵";
      } else if (ev.type === "skill_trigger") {
        li.className = "log-entry";
        const skill = ev.skill || {};
        const effect = skill.amount
          ? `<span class="log-effects"><span class="fx-courage-up">AP +${esc(skill.amount)}</span></span>`
          : skill.description
            ? `<span class="log-effects">${esc(skill.description)}</span>`
            : "";
        li.innerHTML = `<span class="log-skill">✦ 特技 · ${esc(skill.name || "")}</span>
          <span class="log-owner">${esc(skill.warrior || "")}</span>
          ${effect}`;
      } else if (ev.type === "attack") {
        li.className = "log-entry";
        const defense = ev.defense || {};
        const fx = [];
        ["A", "B"].forEach((side) => {
          const tags = effectTags(ev, side);
          if (tags) {
            const name = side === "A" ? S.warriors.A.name : S.warriors.B.name;
            fx.push(`<span class="log-owner">${esc(name)}</span>${tags}`);
          }
        });
        const dead = deadNames(ev);
        if (dead.length) li.classList.add("is-death");
        li.innerHTML =
          `<span class="log-actor">${esc(ev.actor.name)}</span>进攻 → <span class="log-defender">${esc(ev.defender.name)}</span>` +
          `<span class="def-word">${esc(defense.label || "")}</span>` +
          `<span class="def-result ${defense.success ? "is-success" : "is-fail"}">${defense.success ? "成功" : "失败"}</span>` +
          (fx.length ? `<span class="log-effects">${fx.join(" · ")}</span>` : "") +
          (dead.length ? `<span class="log-death">☠ ${dead.map(esc).join(" / ")} 阵亡</span>` : "");
      } else if (ev.type === "clash") {
        li.className = "log-entry";
        const participants = (ev.clash && ev.clash.participants) || [];
        const fx = [];
        ["A", "B"].forEach((side) => {
          const tags = effectTags(ev, side);
          if (tags) {
            fx.push(`<span class="log-owner">${esc(S.warriors[side].name)}</span>${tags}`);
          }
        });
        li.innerHTML =
          `<span class="log-clash">⚔ 拼刀</span>` +
          `<span class="log-owner">${participants.map(esc).join(" / ")}</span>` +
          (fx.length ? `<span class="log-effects">${fx.join(" · ")}</span>` : "");
      } else if (ev.type === "move") {
        li.className = "log-entry is-meta";
        const mv = ev.move || {};
        const cell = (c) => (c ? `(${c[0]},${c[1]})` : "");
        li.textContent = `${mv.warrior || ""} 移动 ${cell(mv.from)} → ${cell(mv.to)}`;
      } else if (ev.type === "sp_leader_change") {
        li.className = "log-entry is-meta";
        const leader = ev.leader && S.warriors[ev.leader] ? S.warriors[ev.leader].name : "";
        li.textContent = leader ? `体力领先 → ${leader}` : "体力领先易主";
      } else if (ev.type === "battle_end" || ev.type === "timeout") {
        li.className = "log-entry is-result";
        li.textContent = ev.text;
      } else {
        return;
      }

      this.list.appendChild(li);
      if (this.currentEl) this.currentEl.classList.remove("current");
      li.classList.add("current");
      this.currentEl = li;
      if (this.total) {
        this.note.textContent = `事件 ${index + 1} / ${this.total}${ev.round ? ` · 第 ${ev.round} 回合` : ""}`;
      }
      if (!silent) this.scrollToEnd();
    }

    scrollToEnd() {
      window.requestAnimationFrame(() => {
        this.list.scrollTop = this.list.scrollHeight;
      });
    }
  }

  function effectTags(ev, side) {
    const fx = ev.effects && ev.effects[side];
    if (!fx) return "";
    const tags = [];
    if (fx.hp <= -0.5) tags.push(`<span class="fx-hp">HP ${Math.round(fx.hp)}</span>`);
    if (fx.sp <= -0.4) tags.push(`<span class="fx-sp">SP ${Math.round(fx.sp)}</span>`);
    else if (fx.sp >= 0.4) tags.push(`<span class="fx-sp">SP +${Math.round(fx.sp)}</span>`);
    if (fx.courage) {
      const cls = fx.courage > 0 ? "fx-courage-up" : "fx-courage-down";
      tags.push(`<span class="${cls}">胆气 ${fx.courage > 0 ? "+" : ""}${fx.courage}</span>`);
    }
    return tags.join(" ");
  }

  function deadNames(ev) {
    if (!ev.alive) return [];
    const names = [];
    if (ev.alive.A === false) names.push(S.warriors.A.name);
    if (ev.alive.B === false) names.push(S.warriors.B.name);
    return names;
  }

  /* ================= 播放控制 ================= */

  function updatePosition(index) {
    const total = S.events.length;
    const max = Math.max(0, total - 1);
    const clamped = Math.max(0, index);
    els.progress.value = String(clamped);
    els.progress.style.setProperty("--progress", `${max > 0 ? (clamped / max) * 100 : 0}%`);
    els.eventCounter.textContent = index < 0 ? `0 / ${total}` : `${index + 1} / ${total}`;
  }

  function setRoundTick(ev, instant) {
    const round = ev && ev.round ? ev.round : 1;
    const tick = ev ? ev.tick : 0;
    els.roundLabel.textContent = `第 ${round} 回合`;
    els.tickLabel.textContent = `tick ${tick}`;
    els.actionRound.textContent = `第 ${round} 回合`;
    if (!instant && S.lastRound !== round) {
      els.roundLabel.classList.remove("pop");
      void els.roundLabel.offsetWidth;
      els.roundLabel.classList.add("pop");
    }
    S.lastRound = round;
  }

  function formatAction(ev) {
    if (!ev) return "战斗即将开始";
    if (ev.type === "attack") {
      const defense = ev.defense || {};
      return (
        `${esc(ev.actor.name)}进攻 → ${esc(ev.defender.name)}` +
        `<span class="def-inline">${esc(defense.label || "")}</span>` +
        `<span class="${defense.success ? "def-ok" : "def-bad"}">${defense.success ? "成功" : "失败"}</span>`
      );
    }
    if (ev.type === "clash") {
      return `拼刀！${(ev.clash && ev.clash.participants ? ev.clash.participants : []).map(esc).join(" / ")}`;
    }
    return esc(ev.text);
  }

  function setAction(ev) {
    els.actionText.innerHTML = formatAction(ev);
  }

  function isFinished() {
    return S.events.length > 0 && S.cursor >= S.events.length - 1;
  }

  function updateButtons() {
    if (S.playing) {
      els.btnPlay.textContent = S.paused ? "继续" : "暂停";
      els.btnPlay.disabled = false;
    } else if (isFinished()) {
      els.btnPlay.textContent = "已结束";
      els.btnPlay.disabled = true;
    } else {
      els.btnPlay.textContent = S.cursor < 0 ? "开始" : "继续";
      els.btnPlay.disabled = !S.events.length;
    }

    els.btnPrev.disabled = Live.active || S.cursor <= -1;
    els.btnReplay.disabled = Live.active;
    els.btnEnd.disabled = Live.active;
    els.progress.disabled = Live.active;
  }

  function showResult(ev) {
    const battle = S.doc.battle;
    const finalState = ev && ev.state ? ev.state : S.initial;
    const winner = battle.winnerSide;
    els.resultTitle.textContent = winner && S.warriors[winner] ? `${S.warriors[winner].name} 胜` : "平局";
    const seed = S.doc.meta && S.doc.meta.seed;
    els.resultSub.textContent = `${
      battle.outcome === "timeout" ? "超时判定 · " : ""
    }共 ${battle.rounds} 回合 · ${battle.ticks} tick${
      seed === null || seed === undefined ? "" : ` · 种子 ${seed}`
    }`;
    els.resultStats.innerHTML = ["A", "B"]
      .map((side) => {
        const warrior = S.warriors[side];
        const state = finalState[side];
        return `<span>${esc(warrior.name)}<b>HP ${Math.round(state.hp)} · SP ${Math.round(state.sp)}</b></span>`;
      })
      .join("");
    els.resultOverlay.hidden = false;
    showLeadReport(true);
  }

  function hideResult() {
    els.resultOverlay.hidden = true;
    showLeadReport(false);
  }

  function seekTo(index) {
    if (!S.events.length) return;
    S.token += 1;
    S.playing = false;
    S.paused = false;
    S.scene.setPaused(false);

    const last = S.events.length - 1;
    const target = clamp(index, -1, last);
    S.cursor = target;

    const state = target < 0 ? S.initial : S.events[target].state;
    S.scene.restore(state);
    Hud.apply(state, { instant: true });

    if (target < 0) {
      S.log.total = S.events.length;
      S.log.clear();
      setRoundTick(null, true);
      setAction(null);
      hideResult();
      updatePosition(-1);
    } else {
      const ev = S.events[target];
      S.log.rebuild(S.events, target, S.events.length);
      setRoundTick(ev, true);
      setAction(ev);
      updatePosition(target);
      if (target === last) showResult(ev);
      else hideResult();
    }

    updateButtons();
  }

  async function waitForResume(token) {
    return new Promise((resolve) => {
      const check = () => {
        if (token !== S.token) return resolve(false);
        if (!S.paused) return resolve(true);
        window.setTimeout(check, 60);
      };
      check();
    });
  }

  async function startPlayback(fromIndex) {
    if (!S.events.length) return;
    const token = ++S.token;
    S.playing = true;
    S.paused = false;
    S.scene.setPaused(false);
    updateButtons();

    for (let i = Math.max(0, fromIndex); i < S.events.length; i += 1) {
      if (token !== S.token) return;
      if (S.paused) {
        const ok = await waitForResume(token);
        if (!ok || token !== S.token) return;
      }

      const ev = S.events[i];
      const before = i === 0 ? S.initial : S.events[i - 1].state;
      S.cursor = i;

      updatePosition(i);
      S.log.total = S.events.length;
      S.log.add(ev, i);
      setAction(ev);
      setRoundTick(ev, false);

      await S.scene.animateEvent(ev, before, () => {
        if (token !== S.token) return;
        Hud.apply(ev.state, { effects: ev.effects });
      });
      if (token !== S.token) return;

      if (ev.type !== "attack" && ev.type !== "clash") {
        Hud.apply(ev.state, { effects: ev.effects });
      }

      if (ev.type === "battle_end") {
        showResult(ev);
      }

      if (i === S.events.length - 1) {
        if (ev.type !== "battle_end" && ev.type !== "timeout") showResult(ev);
        finishPlayback(token);
        return;
      }

      const next = S.events[i + 1];
      const gap = Math.max(30, Math.min(160, (next.tick - ev.tick) * 1.2)) / S.speed;
      await S.scene.wait(gap);
      if (token !== S.token) return;
    }
    finishPlayback(token);
  }

  function finishPlayback(token) {
    if (token !== undefined && token !== S.token) return;
    S.playing = false;
    S.paused = false;
    S.scene.setPaused(false);
    updateButtons();
  }

  function replay() {
    seekTo(-1);
    window.setTimeout(() => startPlayback(0), 220);
  }

  function startOrResume() {
    if (!S.events.length) return;
    if (S.playing) {
      if (S.paused) {
        S.paused = false;
        S.scene.setPaused(false);
        updateButtons();
      }
      return;
    }
    if (isFinished()) return;
    startPlayback(S.cursor + 1);
  }

  function togglePlay() {
    if (S.playing) togglePause();
    else startOrResume();
  }

  function togglePause() {
    if (!S.playing) return;
    S.paused = !S.paused;
    S.scene.setPaused(S.paused);
    updateButtons();
  }

  function isBattleDocument(doc) {
    return Boolean(
      doc &&
        doc.warriors &&
        doc.warriors.A &&
        doc.warriors.B &&
        Array.isArray(doc.events) &&
        doc.events.length
    );
  }

  function applyDocument(doc, options = {}) {
    S.token += 1;
    S.playing = false;
    S.paused = false;
    S.lastRound = null;
    S.doc = doc;
    S.events = doc.events;
    S.warriors = doc.warriors;
    S.initial = initialState(doc);

    S.scene.init(doc);
    Hud.init(doc);
    S.log = new LogView();
    renderLeadReport(doc);
    $("btn-range").classList.remove("is-active");

    els.progress.max = String(Math.max(0, S.events.length - 1));
    els.progress.value = "0";
    seekTo(-1);

    if (options.autoplay) {
      const current = doc;
      const delay = options.delay === undefined ? 320 : options.delay;
      window.setTimeout(() => {
        if (S.doc === current && S.cursor === -1 && !S.playing) startPlayback(0);
      }, delay);
    }
  }

  /* ================= 实时操控 ================= */

  const Live = {
    active: false,
    sessionId: null,
    events: [],
    queue: [],
    prevState: null,
    playedIndex: -1,
    finished: false,
    battle: null,
    modes: { A: "auto", B: "auto" },
    activeSide: "A",
    keys: new Set(),
    attackPending: { A: false, B: false },
    state: null,
    tickDebt: 0,
    lastPoll: 0,
    replayDoc: null,
  };

  const LIVE_POLL_MS = 120;
  // TICK_RATE=0.05 → 每秒 20 tick 时游戏时间与真实时间 1:1，倍速按 S.speed 放大
  const LIVE_TICKS_PER_SEC = 20;
  const MOVE_KEYS = {
    KeyW: [0, -1], ArrowUp: [0, -1],
    KeyS: [0, 1], ArrowDown: [0, 1],
    KeyA: [-1, 0], ArrowLeft: [-1, 0],
    KeyD: [1, 0], ArrowRight: [1, 0],
  };

  async function startLive() {
    if (Live.active || !S.doc) return;
    const params = new URLSearchParams();
    ["A", "B"].forEach((side) => {
      const warrior = S.doc.warriors[side];
      const key = side.toLowerCase();
      params.set(`${key}_warrior`, warrior.name);
      const infos = warrior.skillInfo || [];
      params.set(
        `${key}_skills`,
        infos.map((info) => `${info.id}:${info.enabled === false ? 0 : 1}`).join(",")
      );
    });
    els.btnLive.disabled = true;
    try {
      const response = await fetch(API_BASE + "api/session/new?" + params.toString(), {
        cache: "no-store",
      });
      const data = await response.json().catch(() => null);
      if (!response.ok) throw new Error((data && data.error) || `HTTP ${response.status}`);
      enterLive(data.sessionId, data.doc);
    } catch (error) {
      console.error("进入实时操控失败:", error);
      const hint = /fetch/i.test(error.message)
        ? "实时操控需要本地服务：python main.py --serve-web"
        : `无法进入实时操控：${error.message}`;
      S.scene.toast(hint, { center: true });
    } finally {
      els.btnLive.disabled = false;
    }
  }

  function enterLive(sessionId, doc) {
    Live.replayDoc = S.doc;
    Live.sessionId = sessionId;
    Live.events = doc.events.slice();
    Live.queue = doc.events.slice();
    Live.playedIndex = -1;
    Live.prevState = initialState(doc);
    Live.finished = false;
    Live.battle = null;
    Live.modes = { A: "auto", B: "auto" };
    Live.activeSide = "A";
    Live.keys.clear();
    Live.attackPending = { A: false, B: false };
    Live.state = null;
    Live.tickDebt = 0;
    Live.lastPoll = performance.now();

    applyDocument(doc, { autoplay: false });
    S.events = Live.events;
    Live.active = true;
    setLiveUI(true);
    const token = S.token;
    liveAnimate(token);
    livePoll(token);
    liveRender(token);
  }

  function teardownLiveSession() {
    if (Live.sessionId) {
      fetch(API_BASE + "api/session/close", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sessionId: Live.sessionId }),
      }).catch(() => {});
    }
    Live.sessionId = null;
    Live.active = false;
    Live.keys.clear();
    ["A", "B"].forEach((side) => S.scene.units[side].classList.remove("moving"));
    setLiveUI(false);
  }

  function exitLive() {
    const doc = Live.replayDoc;
    teardownLiveSession();
    if (doc) applyDocument(doc, { autoplay: true, delay: 300 });
  }

  function setLiveUI(on) {
    els.btnLive.textContent = on ? "退出操控" : "实时操控";
    els.btnLive.classList.toggle("is-active", on);
    els.liveHint.hidden = !on;
    els.progressHint.textContent = on
      ? "实时操控中 · 战斗结束后仍可拖动回放"
      : "可拖动定位任意事件";
    els.logNote.textContent = on ? "实时战报 · 键盘操控中" : "按事件回放 · 可前后拖动";
    ["A", "B"].forEach((side) => {
      $("btn-mode-" + side).disabled = !on;
      $("ap-gauge-" + side).hidden = !on;
      $("control-active-" + side).hidden = true;
      $("fighter-" + side).classList.remove("is-controlled");
      S.scene.units[side].classList.remove("is-controlled");
    });
    if (on) {
      updateModeButtons();
      setActiveSide(Live.activeSide);
    }
    updateButtons();
  }

  function updateModeButtons() {
    ["A", "B"].forEach((side) => {
      const button = $("btn-mode-" + side);
      const manual = Live.modes[side] === "manual";
      button.textContent = manual ? "手动" : "自动";
      button.classList.toggle("is-manual", manual);
      button.title = manual
        ? "手动模式：仅响应键盘移动 / 攻击指令（点击切回自动）"
        : "自动模式：AI 托管，键盘指令优先（点击切为手动）";
    });
  }

  function toggleMode(side) {
    if (!Live.active) return;
    Live.modes[side] = Live.modes[side] === "manual" ? "auto" : "manual";
    updateModeButtons();
    S.scene.toast(
      `${S.warriors[side].name} · ${Live.modes[side] === "manual" ? "手动操控" : "自动托管"}`,
      { side }
    );
  }

  function setActiveSide(side) {
    if (!Live.active) return;
    Live.activeSide = side;
    ["A", "B"].forEach((item) => {
      const on = item === side;
      $("fighter-" + item).classList.toggle("is-controlled", on);
      S.scene.units[item].classList.toggle("is-controlled", on);
      $("control-active-" + item).hidden = !on;
    });
  }

  function liveMoveDir() {
    let dx = 0;
    let dy = 0;
    Live.keys.forEach((code) => {
      const delta = MOVE_KEYS[code];
      if (delta) {
        dx += delta[0];
        dy += delta[1];
      }
    });
    dx = clamp(dx, -1, 1);
    dy = clamp(dy, -1, 1);
    return dx || dy ? [dx, dy] : null;
  }

  function buildLiveCommands() {
    const dir = liveMoveDir();
    const commands = {};
    ["A", "B"].forEach((side) => {
      commands[side] = {
        mode: Live.modes[side],
        move: side === Live.activeSide ? dir : null,
        attack: Live.attackPending[side],
      };
      Live.attackPending[side] = false;
    });
    return commands;
  }

  function updateApGauges() {
    if (!Live.state) return;
    ["A", "B"].forEach((side) => {
      const entry = Live.state[side];
      if (!entry || !entry.ap) return;
      const gauge = $("ap-gauge-" + side);
      gauge.querySelector(".gauge-fill").style.width = `${(entry.ap.percent * 100).toFixed(1)}%`;
      gauge.classList.toggle("is-ready", entry.ap.ready);
      gauge.classList.toggle("is-backswing", entry.ap.phase === "backswing");
      const label = entry.ap.ready ? "可攻击" : entry.ap.phase === "backswing" ? "收招" : "蓄力";
      $("ap-value-" + side).textContent = label;
      gauge.title = entry.ap.ready
        ? "可攻击：按 J 出手"
        : entry.ap.phase === "backswing"
          ? "后摇恢复中"
          : "前摇蓄力中";
    });
  }

  function pressAttack() {
    const side = Live.activeSide;
    Live.attackPending[side] = true;
    const entry = Live.state && Live.state[side];
    if (!entry || !entry.ap || entry.ap.ready) return;
    const other = Live.state[side === "A" ? "B" : "A"];
    const reach = (S.warriors[side].weapon && S.warriors[side].weapon.reach) || 1;
    let dist = 0;
    if (entry.position && other && other.position) {
      dist = Math.max(
        Math.abs(entry.position[0] - other.position[0]),
        Math.abs(entry.position[1] - other.position[1])
      );
    }
    const text =
      entry.ap.phase === "backswing" ? "收招中…" : dist > reach ? "射程外…" : "蓄力中…";
    S.scene.toast(text, { side });
  }

  async function livePoll(token) {
    while (Live.active && !Live.finished && token === S.token) {
      const now = performance.now();
      const dt = Math.min(0.5, (now - Live.lastPoll) / 1000);
      Live.lastPoll = now;
      if (!S.paused) {
        Live.tickDebt += dt * LIVE_TICKS_PER_SEC * S.speed;
        const ticks = Math.min(40, Math.floor(Live.tickDebt));
        if (ticks >= 1) {
          Live.tickDebt -= ticks;
          try {
            const response = await fetch(API_BASE + "api/session/step", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                sessionId: Live.sessionId,
                ticks,
                commands: buildLiveCommands(),
              }),
            });
            const data = await response.json().catch(() => null);
            if (!response.ok) throw new Error((data && data.error) || `HTTP ${response.status}`);
            if (token !== S.token || !Live.active) return;
            if (data.events.length) {
              Live.events.push(...data.events);
              Live.queue.push(...data.events);
            }
            Live.state = data.state;
            updateApGauges();
            if (data.finished) {
              Live.finished = true;
              Live.battle = data.battle;
            }
          } catch (error) {
            if (token !== S.token || !Live.active) return;
            console.error("实时推进失败:", error);
            S.scene.toast("实时连接中断，已退出操控", { center: true });
            exitLive();
            return;
          }
        }
      }
      await new Promise((resolve) => window.setTimeout(resolve, LIVE_POLL_MS));
    }
  }

  /** 逐帧按最新轮询状态连续摆放武将：格内进度插值 + 帧间外推，按键后立即平滑移动 */
  function liveRender(token) {
    let last = performance.now();
    const frame = (now) => {
      if (!Live.active || token !== S.token) return;
      const dt = Math.min(0.25, (now - last) / 1000);
      last = now;
      if (Live.state && !S.paused) {
        S.scene.liveTick(Live.state, dt * S.speed);
      }
      window.requestAnimationFrame(frame);
    };
    window.requestAnimationFrame(frame);
  }

  async function liveAnimate(token) {
    S.playing = true;
    S.paused = false;
    S.scene.setPaused(false);
    updateButtons();
    while (Live.active && token === S.token) {
      if (S.paused) {
        const ok = await waitForResume(token);
        if (!ok || token !== S.token) return;
      }
      const ev = Live.queue.shift();
      if (!ev) {
        if (Live.finished) {
          finishLive(S.events[S.events.length - 1]);
          return;
        }
        await new Promise((resolve) => window.setTimeout(resolve, 60));
        continue;
      }
      Live.playedIndex += 1;
      const before = Live.prevState;
      Live.prevState = ev.state;
      S.cursor = Live.playedIndex;
      S.log.total = Live.events.length;
      S.log.add(ev, Live.playedIndex);
      setAction(ev);
      setRoundTick(ev, false);
      updatePosition(Live.playedIndex);

      if (Live.queue.length > 6) {
        // 积压过多时快进追平：直接落状态，不再逐条演出
        S.scene.restore(ev.state);
        Hud.apply(ev.state, { instant: true });
      } else if (ev.type === "move") {
        // 实时操控下站位由 liveRender 连续插值，move 事件不再逐格补间，避免演出排队叠加延迟
        Hud.apply(ev.state, { effects: ev.effects });
      } else {
        await S.scene.animateEvent(ev, before, () => {
          if (token !== S.token) return;
          Hud.apply(ev.state, { effects: ev.effects });
        });
        if (token !== S.token) return;
        if (ev.type !== "attack" && ev.type !== "clash") {
          Hud.apply(ev.state, { effects: ev.effects });
        }
      }

      if ((ev.type === "battle_end" || ev.type === "timeout") && Live.finished) {
        finishLive(ev);
        return;
      }
    }
  }

  function finishLive(ev) {
    Live.finished = true;
    S.doc.battle = Live.battle;
    // 完整录制写回文档，保证之后退出操控 / 再开局时恢复的回放是整场战斗
    S.doc.events = Live.events;
    els.progress.max = String(Math.max(0, S.events.length - 1));
    renderLeadReport(S.doc);
    teardownLiveSession();
    S.playing = false;
    S.paused = false;
    S.scene.setPaused(false);
    showResult(ev);
    updateButtons();
  }

  /* ================= 新局配置 ================= */

  const Setup = {
    options: null,
    loading: null,
    sides: { A: null, B: null },
    pending: false,
  };

  function loadSetupOptions() {
    if (Setup.options) return Promise.resolve(Setup.options);
    if (!Setup.loading) {
      Setup.loading = fetch(API_BASE + "api/options", { cache: "no-store" })
        .then((response) => {
          if (!response.ok) throw new Error(`HTTP ${response.status}`);
          return response.json();
        })
        .then((options) => {
          Setup.options = options;
          return options;
        })
        .catch((error) => {
          Setup.loading = null;
          throw error;
        });
    }
    return Setup.loading;
  }

  function presetByName(name) {
    return Setup.options.warriors.find((item) => item.name === name) || null;
  }

  function skillsForWarrior(name) {
    return Setup.options.skills.filter(
      (skill) => !skill.owner || skill.owner === name
    );
  }

  function sideConfigFromDefaults(side) {
    const defaults = Setup.options.defaults[side.toLowerCase()] || {};
    const warrior =
      defaults.warrior && presetByName(defaults.warrior)
        ? defaults.warrior
        : Setup.options.warriors[0].name;
    const skills = {};
    Setup.options.skills.forEach((skill) => {
      const presetEnabled = defaults.skills ? defaults.skills[skill.id] : undefined;
      skills[skill.id] = {
        equipped: presetEnabled !== undefined,
        enabled: presetEnabled !== false,
      };
    });
    return { warrior, skills };
  }

  function resetSetupSides() {
    Setup.sides.A = sideConfigFromDefaults("A");
    Setup.sides.B = sideConfigFromDefaults("B");
  }

  function selectSetupWarrior(side, name) {
    const config = Setup.sides[side];
    if (config.warrior === name) return;
    config.warrior = name;
    const preset = presetByName(name);
    Setup.options.skills.forEach((skill) => {
      const presetEnabled = preset.skills[skill.id];
      config.skills[skill.id] = {
        equipped: presetEnabled !== undefined,
        enabled: presetEnabled !== false,
      };
    });
    renderSetupSide(side);
  }

  function renderSetupSide(side) {
    const config = Setup.sides[side];
    $("warrior-chips-" + side).innerHTML = Setup.options.warriors
      .map((warrior) => {
        const selected = warrior.name === config.warrior;
        const portrait = window.WarriorArt.createPortrait(
          window.WarriorArt.resolveStyle(warrior.name)
        );
        return `<button type="button" class="warrior-chip${selected ? " is-selected" : ""}" data-warrior="${esc(warrior.name)}" aria-pressed="${selected}">
          <span class="chip-portrait">${portrait}</span>
          <span class="chip-name">${esc(warrior.name)}</span>
        </button>`;
      })
      .join("");

    const preset = presetByName(config.warrior);
    const labels = Setup.options.statLabels || {};
    const statsHtml = Object.entries(preset.stats)
      .map(
        ([field, value]) =>
          `<span>${esc(labels[field] || field)} <b>${esc(value)}</b></span>`
      )
      .join("");
    $("setup-stats-" + side).innerHTML =
      statsHtml +
      (preset.weapon ? `<span>兵器 <b>${esc(preset.weapon)}</b></span>` : "");

    $("skill-list-" + side).innerHTML = Setup.options.skills
      .map((skill) => {
        const state = config.skills[skill.id];
        const available = !skill.owner || skill.owner === config.warrior;
        const category = skill.owner ? `专属 · ${skill.owner}` : skill.category;
        const switchHtml = available
          ? `<button type="button" class="skill-switch${state.enabled ? " is-on" : ""}" data-skill="${esc(skill.id)}"${state.equipped ? "" : " hidden"}>${state.enabled ? "启用中" : "已关闭"}</button>`
          : "";
        return `<div class="skill-row${available ? "" : " is-locked"}${state.equipped && available ? "" : " is-off"}">
          <label class="skill-check">
            <input type="checkbox" data-skill="${esc(skill.id)}"${state.equipped && available ? " checked" : ""}${available ? "" : " disabled"} />
            <span class="skill-name">${esc(skill.name)}<em class="skill-cat">${esc(category)}</em></span>
          </label>
          ${switchHtml}
          <p class="skill-desc">${esc(skill.description)}${available ? "" : `（仅 ${esc(skill.owner)} 可装备）`}</p>
        </div>`;
      })
      .join("");
  }

  function renderSetup() {
    renderSetupSide("A");
    renderSetupSide("B");
  }

  function showSetupError(message) {
    els.setupError.textContent = message;
    els.setupError.hidden = false;
  }

  async function openSetup() {
    if (S.playing && !S.paused) togglePause();
    els.setupOverlay.hidden = false;
    els.setupError.hidden = true;
    try {
      await loadSetupOptions();
    } catch (error) {
      console.error("加载武将配置失败:", error);
      showSetupError("无法加载武将配置，请确认已运行 python main.py --serve-web");
      return;
    }
    if (!Setup.sides.A || !Setup.sides.B) resetSetupSides();
    renderSetup();
  }

  function closeSetup() {
    els.setupOverlay.hidden = true;
  }

  async function startSetupBattle() {
    if (Setup.pending) return;
    Setup.pending = true;
    els.btnSetupStart.disabled = true;
    els.btnSetupStart.textContent = "生成中…";
    els.setupError.hidden = true;
    try {
      const params = new URLSearchParams();
      ["A", "B"].forEach((side) => {
        const config = Setup.sides[side];
        const key = side.toLowerCase();
        params.set(`${key}_warrior`, config.warrior);
        const available = new Set(
          skillsForWarrior(config.warrior).map((skill) => skill.id)
        );
        const skills = Object.entries(config.skills)
          .filter(([id, state]) => state.equipped && available.has(id))
          .map(([id, state]) => (state.enabled ? id : `${id}:0`));
        params.set(`${key}_skills`, skills.join(","));
      });
      const response = await fetch(API_BASE + "api/battle?" + params.toString(), {
        cache: "no-store",
      });
      const doc = await response.json().catch(() => null);
      if (!response.ok) throw new Error((doc && doc.error) || `HTTP ${response.status}`);
      if (!isBattleDocument(doc)) throw new Error("战斗数据格式不正确");
      closeSetup();
      if (Live.active) teardownLiveSession();
      applyDocument(doc, { autoplay: true });
      els.actionText.textContent = "新战局已生成，战斗即将开始";
    } catch (error) {
      console.error("生成新战局失败:", error);
      showSetupError(error.message || "生成新战局失败，请确认本地服务仍在运行");
    } finally {
      Setup.pending = false;
      els.btnSetupStart.disabled = false;
      els.btnSetupStart.textContent = "开战";
    }
  }

  function bindSetupControls() {
    $("btn-setup-close").addEventListener("click", closeSetup);
    $("btn-setup-cancel").addEventListener("click", closeSetup);
    $("btn-setup-reset").addEventListener("click", () => {
      if (!Setup.options) return;
      resetSetupSides();
      els.setupError.hidden = true;
      renderSetup();
    });
    els.btnSetupStart.addEventListener("click", startSetupBattle);
    els.setupOverlay.addEventListener("click", (event) => {
      if (event.target === els.setupOverlay) closeSetup();
    });

    ["A", "B"].forEach((side) => {
      $("warrior-chips-" + side).addEventListener("click", (event) => {
        const chip = event.target.closest(".warrior-chip");
        if (chip) selectSetupWarrior(side, chip.dataset.warrior);
      });
      $("skill-list-" + side).addEventListener("change", (event) => {
        const input = event.target;
        if (!input.matches("input[data-skill]")) return;
        const state = Setup.sides[side].skills[input.dataset.skill];
        state.equipped = input.checked;
        if (input.checked) state.enabled = true;
        renderSetupSide(side);
      });
      $("skill-list-" + side).addEventListener("click", (event) => {
        const button = event.target.closest(".skill-switch");
        if (!button) return;
        const state = Setup.sides[side].skills[button.dataset.skill];
        state.enabled = !state.enabled;
        renderSetupSide(side);
      });
    });
  }

  /* ================= 初始化 ================= */

  async function loadBattle() {
    try {
      const response = await fetch("data/battle.json", { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return await response.json();
    } catch (error) {
      if (window.BATTLE_DATA) return window.BATTLE_DATA;
      throw error;
    }
  }

  function bindControls() {
    els.btnPlay.addEventListener("click", togglePlay);
    els.btnNew.addEventListener("click", openSetup);
    els.btnLive.addEventListener("click", () => {
      if (Live.active) exitLive();
      else startLive();
    });
    els.btnReplay.addEventListener("click", replay);
    els.btnPrev.addEventListener("click", () => seekTo(S.cursor - 1));
    els.btnEnd.addEventListener("click", () => seekTo(S.events.length - 1));
    $("btn-range").addEventListener("click", (event) => {
      const on = S.scene.toggleRange();
      event.currentTarget.classList.toggle("is-active", on);
    });
    $("btn-result-replay").addEventListener("click", replay);
    els.btnResultNew.addEventListener("click", openSetup);
    bindSetupControls();

    ["A", "B"].forEach((side) => {
      $("btn-mode-" + side).addEventListener("click", () => toggleMode(side));
      S.scene.units[side].addEventListener("click", () => setActiveSide(side));
      $("fighter-" + side).addEventListener("click", (event) => {
        if (event.target.closest("button")) return;
        setActiveSide(side);
      });
    });

    document.querySelectorAll(".speed-btn").forEach((button) => {
      button.addEventListener("click", () => {
        S.speed = Number(button.dataset.speed) || 1;
        S.scene.setSpeed(S.speed);
        document.querySelectorAll(".speed-btn").forEach((item) => {
          item.classList.toggle("is-active", item === button);
        });
        updateButtons();
      });
    });

    els.progress.addEventListener("input", () => {
      seekTo(Number(els.progress.value));
    });

    $("btn-log-toggle").addEventListener("click", (event) => {
      const collapsed = els.logPanel.classList.toggle("is-collapsed");
      event.currentTarget.textContent = collapsed ? "展开" : "收起";
    });

    document.addEventListener("keydown", (event) => {
      if (!els.setupOverlay.hidden) {
        if (event.key === "Escape") closeSetup();
        return;
      }
      if (event.target && event.target.tagName === "INPUT") return;
      if (Live.active) {
        if (MOVE_KEYS[event.code]) {
          event.preventDefault();
          Live.keys.add(event.code);
          return;
        }
        if (event.code === "KeyJ") {
          event.preventDefault();
          if (!event.repeat) pressAttack();
          return;
        }
        if (event.code === "Digit1" || event.code === "Numpad1") {
          setActiveSide("A");
          return;
        }
        if (event.code === "Digit2" || event.code === "Numpad2") {
          setActiveSide("B");
          return;
        }
        if (event.code === "Tab") {
          event.preventDefault();
          setActiveSide(Live.activeSide === "A" ? "B" : "A");
          return;
        }
      }
      if (event.key === " ") {
        event.preventDefault();
        togglePlay();
      } else if (event.key === "ArrowLeft") {
        event.preventDefault();
        seekTo(S.cursor - 1);
      } else if (event.key === "ArrowRight") {
        event.preventDefault();
        seekTo(S.cursor + 1);
      }
    });

    document.addEventListener("keyup", (event) => {
      Live.keys.delete(event.code);
    });
    window.addEventListener("blur", () => Live.keys.clear());
  }

  async function boot() {
    let doc = null;
    try {
      doc = await loadBattle();
    } catch (error) {
      console.error("加载战斗数据失败:", error);
      els.emptyState.hidden = false;
      return;
    }

    if (!isBattleDocument(doc)) {
      els.emptyState.hidden = false;
      return;
    }

    S.scene = new window.BattleScene();
    bindControls();
    applyDocument(doc, { autoplay: true, delay: 700 });
    updateButtons();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
