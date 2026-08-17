const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

const state = {
  user: null,
  meta: null,
  route: "dashboard",
  params: {},
  charts: [],
};

const NAV = [
  ["dashboard", "▦", "Дашборд"],
  ["schedule", "◷", "Расписание"],
  ["queue", "☰", "Очередь"],
  ["patients", "☺", "Пациенты"],
  ["visits", "✎", "Приёмы / ЭМК"],
  ["lab", "⚗", "Лаборатория"],
  ["pharmacy", "💊", "Назначения"],
  ["billing", "₽", "Касса"],
  ["chat", "✉", "Чат"],
  ["inventory", "▦", "Склад"],
  ["tasks", "✓", "Задачи"],
  ["reports", "◉", "Отчёты"],
  ["structure", "⬡", "Структура CRM"],
  ["settings", "⚙", "Настройки"],
];

const STATUS = {
  scheduled: ["Записан", "gray"],
  confirmed: ["Подтверждён", "blue"],
  waiting: ["Ожидает", "warn"],
  in_progress: ["На приёме", "violet"],
  completed: ["Завершён", ""],
  cancelled: ["Отменён", "bad"],
  no_show: ["Не явился", "bad"],
};

const LAB_STATUS = {
  ordered: ["Назначен", "blue"],
  processing: ["В работе", "warn"],
  ready: ["Готов", ""],
};

function esc(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function money(n) {
  return `${Number(n || 0).toLocaleString("ru-RU")} ₽`;
}

function initials(name) {
  return (name || "?")
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((x) => x[0])
    .join("")
    .toUpperCase();
}

function fmtTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso.replace(" ", "T"));
  return d.toLocaleString("ru-RU", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

function hhmm(iso) {
  return (iso || "").slice(11, 16);
}

function toast(text) {
  const el = $("#toast");
  el.textContent = text;
  el.classList.remove("hidden");
  setTimeout(() => el.classList.add("hidden"), 2600);
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    credentials: "same-origin",
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  const data = await res.json().catch(() => ({ ok: false, error: "Ошибка сети" }));
  if (res.status === 401) {
    state.user = null;
    showLogin();
    throw new Error(data.error || "Нужна авторизация");
  }
  if (!data.ok) throw new Error(data.error || "Ошибка");
  return data.data;
}

function pill(status, map = STATUS) {
  const [label, kind] = map[status] || [status, "gray"];
  return `<span class="pill ${kind}">${esc(label)}</span>`;
}

function openModal(html) {
  $("#modal-card").innerHTML = html;
  $("#modal").classList.remove("hidden");
}
function closeModal() {
  $("#modal").classList.add("hidden");
}
$("#modal").addEventListener("click", (e) => {
  if (e.target.id === "modal") closeModal();
});

function destroyCharts() {
  state.charts.forEach((c) => c.destroy());
  state.charts = [];
}

function chart(id, cfg) {
  const ctx = document.getElementById(id);
  if (!ctx || !window.Chart) return;
  state.charts.push(new Chart(ctx, cfg));
}

function parseHash() {
  const raw = (location.hash || "#/dashboard").replace(/^#\/?/, "");
  const [pathPart] = raw.split("?");
  const [route, ...rest] = pathPart.split("/");
  state.route = route || "dashboard";
  state.params = { id: rest[0] };
}

function go(path) {
  location.hash = "#/" + path.replace(/^#\/?/, "");
}

function navHtml() {
  return NAV.map(
    ([id, ico, label]) =>
      `<a href="#/${id}" class="${state.route === id || (id === "patients" && state.route === "patient") ? "active" : ""}"><span class="ico">${ico}</span>${label}</a>`
  ).join("");
}

function showLogin() {
  $("#app-root").classList.add("hidden");
  $("#login-root").classList.remove("hidden");
}

function showApp() {
  $("#login-root").classList.add("hidden");
  $("#app-root").classList.remove("hidden");
  $("#nav").innerHTML = navHtml();
  const u = state.user;
    $("#sidebar-user").innerHTML = `
    <div class="ava" style="background:${u.color}">${esc(initials(u.full_name))}</div>
    <div><strong>${esc(u.full_name)}</strong><small>${esc(u.specialty || roleName(u.role))}</small></div>`;
}

function roleName(r) {
  return { admin: "главный врач", doctor: "врач", reception: "регистратура", nurse: "медсестра", accountant: "касса" }[r] || r;
}

function optionList(items, valueKey, labelKey, selected) {
  return items.map((x) => `<option value="${x[valueKey]}" ${String(x[valueKey]) === String(selected) ? "selected" : ""}>${esc(x[labelKey])}</option>`).join("");
}

function patientOptions(patients, selected) {
  return patients
    .map((p) => `<option value="${p.id}" ${String(p.id) === String(selected) ? "selected" : ""}>${esc(p.full_name)} · ${esc(p.card_no)}</option>`)
    .join("");
}

async function loadMeta() {
  state.meta = await api("/api/meta");
}

$("#login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  $("#login-error").textContent = "";
  try {
    state.user = await api("/api/login", {
      method: "POST",
      body: { email: fd.get("email"), password: fd.get("password") },
    });
    await loadMeta();
    showApp();
    parseHash();
    render();
  } catch (err) {
    $("#login-error").textContent = err.message;
  }
});

$$("[data-demo]").forEach((btn) => {
  btn.addEventListener("click", () => {
    const [email, password] = btn.dataset.demo.split("|");
    $("#login-form [name=email]").value = email;
    $("#login-form [name=password]").value = password;
  });
});

$("#btn-logout").addEventListener("click", async () => {
  await api("/api/logout", { method: "POST" });
  state.user = null;
  showLogin();
});

$("#btn-new-appt").addEventListener("click", () => formAppointment());
$("#global-search").addEventListener("keydown", (e) => {
  if (e.key === "Enter") go("patients?q=" + encodeURIComponent(e.target.value));
});

window.addEventListener("hashchange", () => {
  parseHash();
  render();
});

async function boot() {
  try {
    state.user = await api("/api/me");
    await loadMeta();
    showApp();
    parseHash();
    render();
  } catch {
    showLogin();
  }
}

async function render() {
  destroyCharts();
  $("#nav").innerHTML = navHtml();
  const titles = Object.fromEntries(NAV.map((x) => [x[0], x[2]]));
  $("#crumb").textContent = "Семейный доктор · CRM";
  $("#page-title").textContent = titles[state.route] || (state.route === "patient" ? "Карточка пациента" : "CRM");
  const view = $("#view");
  view.innerHTML = `<div class="card empty">Загрузка…</div>`;
  try {
    const fn = routes[state.route] || routes.dashboard;
    await fn(view);
  } catch (err) {
    view.innerHTML = `<div class="card empty">${esc(err.message)}</div>`;
  }
}

const routes = {};

routes.dashboard = async (view) => {
  const d = await api("/api/dashboard");
  const k = d.kpis;
  view.innerHTML = `
    <div class="grid kpis">
      ${kpi("Пациентов в базе", k.patients, "картотека клиники")}
      ${kpi("Записей сегодня", k.today, k.waiting + " в очереди")}
      ${kpi("Выручка дня", money(k.revenue_today), "открытые счета: " + money(k.open_invoices))}
      ${kpi("Внимание", k.unread + " сообщ. · " + k.lab_pending + " анализов", "чат и лаборатория")}
    </div>
    <div class="grid two" style="margin-top:14px">
      <div class="card">
        <h3>Расписание на сегодня</h3>
        <table class="table">
          <thead><tr><th>Время</th><th>Пациент</th><th>Врач</th><th>Услуга</th><th></th></tr></thead>
          <tbody>
            ${d.appointments_today.map((a) => `
              <tr data-go="patient/${a.patient_id}">
                <td>${hhmm(a.start_at)}</td>
                <td>${esc(a.last_name)} ${esc(a.first_name)}</td>
                <td>${esc(a.doctor_name)}</td>
                <td>${esc(a.service_name || "—")}</td>
                <td>${pill(a.status)}</td>
              </tr>`).join("") || emptyRow(5)}
          </tbody>
        </table>
      </div>
      <div>
        <div class="card">
          <h3>Визиты за 14 дней</h3>
          <canvas id="chart-visits" height="120"></canvas>
        </div>
        <div class="card" style="margin-top:14px">
          <h3>Задачи</h3>
          ${d.tasks.slice(0, 6).map((t) => `
            <div class="q-item">
              <div>
                <strong>${esc(t.title)}</strong>
                <div class="meta">${esc(t.assignee_name || "—")} · ${fmtTime(t.due_at)}</div>
              </div>
              ${t.priority === "high" ? '<span class="pill bad">важно</span>' : ""}
            </div>`).join("") || '<div class="empty">Нет открытых задач</div>'}
        </div>
      </div>
    </div>
    <div class="grid two" style="margin-top:14px">
      <div class="card">
        <h3>Выручка</h3>
        <canvas id="chart-rev" height="110"></canvas>
      </div>
      <div class="card">
        <h3>На контроле</h3>
        ${d.watch.map((p) => `
          <div class="q-item" data-go="patient/${p.id}">
            <div class="ava" style="background:#e63946">${esc(initials(p.full_name))}</div>
            <div><strong>${esc(p.full_name)}</strong><div class="meta">${esc(p.chronic)}</div></div>
          </div>`).join("") || '<div class="empty">Нет пациентов на контроле</div>'}
        ${d.low_stock.length ? `<h3 style="margin-top:16px">Склад ниже минимума</h3>` : ""}
        ${d.low_stock.map((x) => `<div class="meta">${esc(x.name)} · ${x.qty} ${esc(x.unit)} из ${x.min_qty}</div>`).join("")}
      </div>
    </div>`;
  bindGoes(view);
  chart("chart-visits", lineCfg(d.visits_series.map((x) => x.date.slice(5)), d.visits_series.map((x) => x.count), "#3d8b4e"));
  chart("chart-rev", lineCfg(d.revenue_series.map((x) => x.date.slice(5)), d.revenue_series.map((x) => x.amount), "#2f6fed"));
};

function kpi(label, value, hint) {
  return `<div class="card kpi"><div class="label">${esc(label)}</div><div class="value">${value}</div><div class="hint">${esc(hint || "")}</div></div>`;
}
function emptyRow(n) {
  return `<tr><td colspan="${n}" class="empty">Пока пусто</td></tr>`;
}
function lineCfg(labels, data, color) {
  return {
    type: "line",
    data: { labels, datasets: [{ data, borderColor: color, backgroundColor: color + "33", fill: true, tension: 0.35, pointRadius: 0 }] },
    options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } },
  };
}
function bindGoes(root) {
  root.addEventListener("click", (e) => {
    const row = e.target.closest("[data-go]");
    if (row) go(row.dataset.go);
  });
}

function mondayOf(d = new Date()) {
  const x = new Date(d);
  const day = (x.getDay() + 6) % 7;
  x.setDate(x.getDate() - day);
  x.setHours(0, 0, 0, 0);
  return x;
}
function isoDate(d) {
  return d.toISOString().slice(0, 10);
}

routes.schedule = async (view) => {
  const start = mondayOf();
  const end = new Date(start);
  end.setDate(end.getDate() + 6);
  const items = await api(`/api/appointments?from=${isoDate(start)}&to=${isoDate(end)}`);
  const hours = [];
  for (let h = 8; h <= 19; h++) hours.push(h);
  const days = [...Array(7)].map((_, i) => {
    const d = new Date(start);
    d.setDate(d.getDate() + i);
    return d;
  });
  const names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
  view.innerHTML = `
    <div class="card" style="margin-bottom:12px;display:flex;justify-content:space-between;align-items:center">
      <div>Неделя ${start.toLocaleDateString("ru-RU")} — ${end.toLocaleDateString("ru-RU")}</div>
      <button class="btn primary" id="new-appt2">+ Записать пациента</button>
    </div>
    <div class="week">
      <div class="head"></div>
      ${days.map((d, i) => `<div class="head ${isoDate(d) === isoDate(new Date()) ? "today" : ""}">${names[i]}<div class="meta">${d.getDate()}.${String(d.getMonth() + 1).padStart(2, "0")}</div></div>`).join("")}
      ${hours.map((h) => `
        <div class="time">${String(h).padStart(2, "0")}:00</div>
        ${days.map((d) => `<div class="cell" data-slot="${isoDate(d)} ${String(h).padStart(2, "0")}:00:00"></div>`).join("")}
      `).join("")}
    </div>`;
  $("#new-appt2").onclick = () => formAppointment();
  items.forEach((a) => {
    const day = a.start_at.slice(0, 10);
    const hour = Number(a.start_at.slice(11, 13));
    const cell = view.querySelector(`.cell[data-slot="${day} ${String(hour).padStart(2, "0")}:00:00"]`);
    if (!cell) return;
    const mins = Number(a.start_at.slice(14, 16));
    const dur = Math.max(28, (new Date(a.end_at.replace(" ", "T")) - new Date(a.start_at.replace(" ", "T"))) / 60000);
    const el = document.createElement("div");
    el.className = "appt";
    el.style.background = a.doctor_color || "#3d8b4e";
    el.style.top = `${(mins / 60) * 42 + 2}px`;
    el.style.height = `${Math.min(dur, 55)}px`;
    el.innerHTML = `${esc(a.last_name)} ${esc((a.first_name || "")[0])}.<small>${esc(a.doctor_name.split(" ")[0])} · ${hhmm(a.start_at)}</small>`;
    el.onclick = (ev) => {
      ev.stopPropagation();
      go("patient/" + a.patient_id);
    };
    cell.appendChild(el);
  });
  $$(".cell", view).forEach((cell) => {
    cell.addEventListener("click", () => formAppointment({ start_at: cell.dataset.slot }));
  });
};

routes.queue = async (view) => {
  const items = await api("/api/queue");
  view.innerHTML = `
    <div class="queue">
      ${items.map((a) => `
        <div class="q-item">
          <div class="when">${hhmm(a.start_at)}</div>
          <div class="ava" style="background:${a.doctor_color || "#3d8b4e"}">${esc(initials(a.last_name + " " + a.first_name))}</div>
          <div style="flex:1">
            <strong>${esc(a.last_name)} ${esc(a.first_name)} ${esc(a.patronymic || "")}</strong>
            <div class="meta">${esc(a.doctor_name)} · ${esc(a.service_name || "приём")} · ${esc(a.complaint || "")}</div>
          </div>
          ${pill(a.status)}
          <button class="btn sm" data-st="waiting" data-id="${a.id}">В очередь</button>
          <button class="btn sm primary" data-st="in_progress" data-id="${a.id}">Пригласить</button>
          <button class="btn sm" data-st="completed" data-id="${a.id}">Завершить</button>
        </div>`).join("") || '<div class="card empty">На сегодня живая очередь пуста</div>'}
    </div>`;
  view.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-st]");
    if (!btn) return;
    await api("/api/appointments/" + btn.dataset.id, { method: "PUT", body: { status: btn.dataset.st } });
    toast("Статус обновлён");
    render();
  });
};

routes.patients = async (view) => {
  const q = new URLSearchParams(location.hash.split("?")[1] || "").get("q") || $("#global-search").value || "";
  const items = await api("/api/patients" + (q ? `?q=${encodeURIComponent(q)}` : ""));
  view.innerHTML = `
    <div class="card" style="margin-bottom:12px;display:flex;gap:10px;align-items:center">
      <input class="search" id="p-search" value="${esc(q)}" placeholder="ФИО, телефон, номер карты" />
      <button class="btn primary" id="p-new">+ Новый пациент</button>
    </div>
    <div class="card">
      <table class="table">
        <thead><tr><th>Карта</th><th>Пациент</th><th>Возраст</th><th>Телефон</th><th>Врач</th><th>Статус</th></tr></thead>
        <tbody>
          ${items.map((p) => `
            <tr data-go="patient/${p.id}">
              <td>${esc(p.card_no)}</td>
              <td><strong>${esc(p.full_name)}</strong><div class="meta">${esc(p.chronic || "без хронических")}</div></td>
              <td>${p.age ?? "—"}</td>
              <td>${esc(p.phone || "—")}</td>
              <td>${esc(p.doctor_name || "не закреплён")}</td>
              <td>${p.status === "watch" ? '<span class="pill warn">контроль</span>' : '<span class="pill">активен</span>'}</td>
            </tr>`).join("")}
        </tbody>
      </table>
    </div>`;
  bindGoes(view);
  $("#p-new").onclick = () => formPatient();
  $("#p-search").addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      $("#global-search").value = e.target.value;
      routes.patients(view);
    }
  });
};

routes.patient = async (view) => {
  const data = await api("/api/patients/" + state.params.id);
  const p = data.patient;
  let tab = "overview";
  const draw = () => {
    view.innerHTML = `
      <div class="card patient-hero">
        <div class="ava" style="width:56px;height:56px;background:${state.meta.doctors.find((d) => d.id === p.doctor_id)?.color || "#3d8b4e"}">${esc(initials(p.full_name))}</div>
        <div style="flex:1">
          <h2>${esc(p.full_name)}</h2>
          <div class="meta">${esc(p.card_no)} · ${p.sex === "female" ? "жен." : "муж."} · ${p.age ?? "—"} лет · ${esc(p.phone || "")} · ${esc(p.insurance || "")}</div>
        </div>
        <button class="btn" id="edit-p">Карточка</button>
        <button class="btn primary" id="appt-p">Записать</button>
      </div>
      <div class="tabs" style="margin-top:14px">
        ${[["overview","Обзор"],["emr","ЭМК"],["lab","Анализы"],["rx","Назначения"],["pay","Счета"],["chat","Чат"]].map(([id,l]) => `<button class="btn sm ${tab===id?"on":""}" data-tab="${id}">${l}</button>`).join("")}
      </div>
      <div id="ptab"></div>`;
    $("#edit-p").onclick = () => formPatient(p);
    $("#appt-p").onclick = () => formAppointment({ patient_id: p.id, doctor_id: p.doctor_id });
    $$("[data-tab]", view).forEach((b) => (b.onclick = () => { tab = b.dataset.tab; draw(); }));
    const box = $("#ptab");
    if (tab === "overview") {
      box.innerHTML = `
        <div class="grid three">
          <div class="card"><h3>Медкарта</h3>
            <div class="meta">Группа крови</div><strong>${esc(p.blood_type || "—")}</strong>
            <div class="meta" style="margin-top:10px">Аллергии</div><strong>${esc(p.allergies || "нет")}</strong>
            <div class="meta" style="margin-top:10px">Хронические</div><div>${esc(p.chronic || "—")}</div>
            <div class="meta" style="margin-top:10px">Операции</div><div>${esc(p.surgeries || "—")}</div>
          </div>
          <div class="card"><h3>Ближайшие визиты</h3>
            ${data.appointments.slice(0,5).map((a)=>`<div class="q-item"><div><strong>${fmtTime(a.start_at)}</strong><div class="meta">${esc(a.doctor_name)} · ${esc(a.service_name||"")}</div></div>${pill(a.status)}</div>`).join("") || '<div class="empty">нет записей</div>'}
          </div>
          <div class="card"><h3>Напоминания</h3>
            ${data.reminders.map((r)=>`<div class="meta">${esc(r.title)} · ${fmtTime(r.due_at)}</div>`).join("") || '<div class="empty">нет</div>'}
            <p class="meta">${esc(p.notes || "")}</p>
          </div>
        </div>`;
    }
    if (tab === "emr") {
      box.innerHTML = `<div class="card" style="margin-bottom:10px"><button class="btn primary" id="new-visit">+ Протокол приёма</button></div>` +
        data.visits.map((v) => `
          <div class="card" style="margin-bottom:10px">
            <div class="meta">${fmtTime(v.created_at)} · ${esc(v.doctor_name)}</div>
            <strong>${esc(v.diagnosis || "без диагноза")}</strong> <span class="pill gray">${esc(v.icd10 || "")}</span>
            <p>${esc(v.complaint || "")}</p>
            <div class="meta">Осмотр: ${esc(v.examination || "—")}</div>
            <div class="meta">Рекомендации: ${esc(v.recommendations || "—")}</div>
            <button class="btn sm" data-edit-visit="${v.id}">Править</button>
          </div>`).join("") || '<div class="card empty">Протоколов пока нет</div>';
      $("#new-visit")?.addEventListener("click", () => formVisit({ patient_id: p.id, doctor_id: p.doctor_id || state.user.id }));
      $$("[data-edit-visit]").forEach((b) => {
        const v = data.visits.find((x) => String(x.id) === b.dataset.editVisit);
        b.onclick = () => formVisit(v, true);
      });
    }
    if (tab === "lab") {
      box.innerHTML = `<div class="card" style="margin-bottom:10px"><button class="btn primary" id="new-lab">+ Назначить анализ</button></div>` +
        data.labs.map(labCard).join("") || '<div class="card empty">Анализов нет</div>';
      $("#new-lab")?.addEventListener("click", () => formLab({ patient_id: p.id }));
    }
    if (tab === "rx") {
      box.innerHTML = `<div class="card" style="margin-bottom:10px"><button class="btn primary" id="new-rx">+ Назначить препарат</button></div>
        <div class="card"><table class="table"><thead><tr><th>Препарат</th><th>Схема</th><th>Курс</th><th>Врач</th></tr></thead><tbody>
        ${data.prescriptions.map((r)=>`<tr><td>${esc(r.medication)}</td><td>${esc(r.dosage)}</td><td>${r.duration_days} дн. × ${r.times_per_day}</td><td>${esc(r.doctor_name)}</td></tr>`).join("")}
        </tbody></table></div>`;
      $("#new-rx").onclick = () => formRx({ patient_id: p.id });
    }
    if (tab === "pay") {
      box.innerHTML = data.invoices.map((i) => `
        <div class="q-item"><div><strong>${esc(i.number)}</strong><div class="meta">${fmtTime(i.created_at)}</div></div>
        <div>${money(i.amount)}</div>${i.status==="paid"?pill("completed"):'<span class="pill warn">к оплате</span>'}
        ${i.status!=="paid"?`<button class="btn sm primary" data-pay="${i.id}">Принять оплату</button>`:""}</div>`).join("") || '<div class="card empty">Счетов нет</div>';
      $$("[data-pay]").forEach((b) => (b.onclick = async () => {
        await api(`/api/invoices/${b.dataset.pay}/pay`, { method: "POST", body: { method: "карта" } });
        toast("Оплата принята");
        routes.patient(view);
      }));
    }
    if (tab === "chat") {
      box.innerHTML = `<div class="card"><div class="chat-log" id="clog">${data.messages.map(msgBubble).join("")}</div>
        <div class="chat-compose"><input id="cmsg" placeholder="Сообщение пациенту…" /><button class="btn primary" id="csend">Отправить</button></div></div>`;
      $("#csend").onclick = async () => {
        const text = $("#cmsg").value.trim();
        if (!text) return;
        await api("/api/messages", { method: "POST", body: { patient_id: p.id, text } });
        routes.patient(view);
      };
    }
  };
  draw();
};

function labCard(l) {
  const results = l.results || [];
  return `<div class="card" style="margin-bottom:10px">
    <div style="display:flex;justify-content:space-between"><strong>${esc(l.test_name)}</strong>${pill(l.status, LAB_STATUS)}</div>
    <div class="meta">${fmtTime(l.ordered_at)} ${l.comment ? "· " + esc(l.comment) : ""}</div>
    ${results.length ? `<table class="table">${results.map((r)=>`<tr><td>${esc(r.name)}</td><td>${esc(r.val)} ${esc(r.unit||"")}</td><td>${esc(r.ref||"")}</td><td>${r.status==="hi"||r.status==="lo"?'<span class="pill bad">отклонение</span>':'<span class="pill">норма</span>'}</td></tr>`).join("")}</table>` : ""}
  </div>`;
}
function msgBubble(m) {
  return `<div class="bubble ${m.sender !== "patient" ? "me" : ""}"><div class="meta">${esc(m.sender_name || m.sender)} · ${fmtTime(m.created_at)}</div>${esc(m.text)}</div>`;
}

routes.visits = async (view) => {
  const items = await api("/api/visits");
  view.innerHTML = `<div class="card"><table class="table"><thead><tr><th>Дата</th><th>Пациент</th><th>Врач</th><th>Диагноз</th><th>МКБ</th></tr></thead><tbody>
    ${items.map((v)=>`<tr data-go="patient/${v.patient_id}"><td>${fmtTime(v.created_at)}</td><td>${esc(v.last_name)} ${esc(v.first_name)}</td><td>${esc(v.doctor_name)}</td><td>${esc(v.diagnosis||"—")}</td><td>${esc(v.icd10||"")}</td></tr>`).join("")}
  </tbody></table></div>`;
  bindGoes(view);
};

routes.lab = async (view) => {
  const items = await api("/api/lab");
  view.innerHTML = `<div class="card" style="margin-bottom:12px"><button class="btn primary" id="lab-new">+ Заказ анализа</button></div>` +
    items.map(labCard).join("");
  $("#lab-new").onclick = () => formLab();
};

routes.pharmacy = async (view) => {
  const patients = await api("/api/patients");
  const rxs = [];
  for (const p of patients.slice(0, 12)) {
    const d = await api("/api/patients/" + p.id);
    d.prescriptions.forEach((r) => rxs.push({ ...r, patient: p.full_name, pid: p.id }));
  }
  view.innerHTML = `<div class="card"><table class="table"><thead><tr><th>Пациент</th><th>Препарат</th><th>Схема</th><th>Курс</th><th>Врач</th></tr></thead><tbody>
    ${rxs.map((r)=>`<tr data-go="patient/${r.pid}"><td>${esc(r.patient)}</td><td>${esc(r.medication)}</td><td>${esc(r.dosage)}</td><td>${r.duration_days} дн.</td><td>${esc(r.doctor_name)}</td></tr>`).join("")}
  </tbody></table></div>`;
  bindGoes(view);
};

routes.billing = async (view) => {
  const items = await api("/api/invoices");
  const open = items.filter((x) => x.status !== "paid").reduce((s, x) => s + (x.amount - x.paid), 0);
  const paid = items.filter((x) => x.status === "paid").reduce((s, x) => s + x.paid, 0);
  view.innerHTML = `
    <div class="grid kpis" style="grid-template-columns:1fr 1fr 1fr">
      ${kpi("Оплачено", money(paid))}
      ${kpi("К оплате", money(open))}
      ${kpi("Счетов", items.length)}
    </div>
    <div class="card" style="margin-top:14px">
      <div style="display:flex;justify-content:space-between;margin-bottom:10px"><h3>Счета</h3><button class="btn primary" id="inv-new">+ Счёт</button></div>
      <table class="table"><thead><tr><th>Номер</th><th>Пациент</th><th>Сумма</th><th>Статус</th><th></th></tr></thead><tbody>
      ${items.map((i)=>`<tr>
        <td>${esc(i.number)}</td><td>${esc(i.last_name)} ${esc(i.first_name)}</td>
        <td>${money(i.amount)}</td><td>${i.status==="paid"?pill("completed"):'<span class="pill warn">открыт</span>'}</td>
        <td>${i.status!=="paid"?`<button class="btn sm primary" data-pay="${i.id}">Оплатить</button>`:esc(i.method||"")}</td>
      </tr>`).join("")}
      </tbody></table>
    </div>`;
  $("#inv-new").onclick = () => formInvoice();
  $$("[data-pay]").forEach((b) => (b.onclick = async () => {
    await api(`/api/invoices/${b.dataset.pay}/pay`, { method: "POST", body: { method: "карта" } });
    toast("Оплата принята");
    render();
  }));
};

routes.chat = async (view) => {
  const threads = await api("/api/messages");
  view.innerHTML = `<div class="chat">
    <div id="threads">${threads.map((t)=>`<div class="thread" data-pid="${t.patient_id}">
      <strong>${esc(t.last_name)} ${esc(t.first_name)}</strong>
      ${t.unread?`<span class="pill bad">${t.unread}</span>`:""}
      <div class="meta">${esc(t.last?.text || "")}</div>
    </div>`).join("")}</div>
    <div><div class="chat-log" id="clog"><div class="empty">Выберите диалог</div></div>
      <div class="chat-compose"><input id="cmsg" placeholder="Ответ…" /><button class="btn primary" id="csend">Отправить</button></div>
    </div>
  </div>`;
  let pid = null;
  async function openThread(id) {
    pid = id;
    $$(".thread").forEach((t) => t.classList.toggle("on", t.dataset.pid === String(id)));
    const msgs = await api("/api/messages?patient_id=" + id);
    $("#clog").innerHTML = msgs.map(msgBubble).join("");
    $("#clog").scrollTop = 9999;
  }
  $$(".thread").forEach((t) => (t.onclick = () => openThread(t.dataset.pid)));
  if (threads[0]) openThread(threads[0].patient_id);
  $("#csend").onclick = async () => {
    if (!pid) return;
    const text = $("#cmsg").value.trim();
    if (!text) return;
    await api("/api/messages", { method: "POST", body: { patient_id: pid, text } });
    $("#cmsg").value = "";
    openThread(pid);
  };
};

routes.inventory = async (view) => {
  const items = await api("/api/inventory");
  view.innerHTML = `<div class="card" style="margin-bottom:12px"><button class="btn primary" id="invadd">+ Позиция</button></div>
    <div class="card"><table class="table"><thead><tr><th>Название</th><th>SKU</th><th>Остаток</th><th>Мин.</th><th>Цена</th><th></th></tr></thead><tbody>
    ${items.map((x)=>`<tr>
      <td>${esc(x.name)}<div class="meta">${esc(x.category)}</div></td>
      <td>${esc(x.sku)}</td>
      <td>${x.qty} ${esc(x.unit)} ${x.qty < x.min_qty ? '<span class="pill bad">мало</span>' : ""}</td>
      <td>${x.min_qty}</td><td>${money(x.price)}</td>
      <td><button class="btn sm" data-plus="${x.id}" data-qty="${x.qty}">+10</button></td>
    </tr>`).join("")}
    </tbody></table></div>`;
  $$("[data-plus]").forEach((b) => (b.onclick = async () => {
    await api("/api/inventory/" + b.dataset.plus, { method: "PUT", body: { qty: Number(b.dataset.qty) + 10 } });
    render();
  }));
  $("#invadd").onclick = () => {
    openModal(`<h3>Новая позиция склада</h3>
      <div class="fields">
        <label class="field">Название<input id="n"></label>
        <label class="field">SKU<input id="s"></label>
        <label class="field">Кол-во<input id="q" type="number" value="10"></label>
        <label class="field">Цена<input id="p" type="number" value="0"></label>
      </div>
      <div class="modal-actions"><button class="btn" id="c">Отмена</button><button class="btn primary" id="ok">Сохранить</button></div>`);
    $("#c").onclick = closeModal;
    $("#ok").onclick = async () => {
      await api("/api/inventory", { method: "POST", body: { name: $("#n").value, sku: $("#s").value, qty: $("#q").value, price: $("#p").value } });
      closeModal(); render();
    };
  };
};

routes.tasks = async (view) => {
  const items = await api("/api/tasks");
  view.innerHTML = `<div class="card" style="margin-bottom:12px"><button class="btn primary" id="tnew">+ Задача</button></div>
    ${items.map((t)=>`<div class="q-item">
      <div style="flex:1"><strong>${esc(t.title)}</strong><div class="meta">${esc(t.assignee_name||"")} · ${esc(t.patient_name||"")} · ${fmtTime(t.due_at)}</div></div>
      ${t.priority==="high"?'<span class="pill bad">важно</span>':""}
      ${pill(t.status==="done"?"completed":"scheduled")}
      ${t.status!=="done"?`<button class="btn sm" data-done="${t.id}">Готово</button>`:""}
    </div>`).join("")}`;
  $$("[data-done]").forEach((b) => (b.onclick = async () => {
    await api("/api/tasks/" + b.dataset.done, { method: "PUT", body: { status: "done" } });
    render();
  }));
  $("#tnew").onclick = () => {
    openModal(`<h3>Задача</h3><div class="fields">
      <label class="field full">Текст<input id="tt"></label>
      <label class="field">Исполнитель<select id="ta">${optionList(state.meta.staff,"id","full_name",state.user.id)}</select></label>
      <label class="field">Приоритет<select id="tp"><option value="normal">обычный</option><option value="high">высокий</option></select></label>
    </div><div class="modal-actions"><button class="btn" id="c">Отмена</button><button class="btn primary" id="ok">Создать</button></div>`);
    $("#c").onclick = closeModal;
    $("#ok").onclick = async () => {
      await api("/api/tasks", { method: "POST", body: { title: $("#tt").value, assignee_id: $("#ta").value, priority: $("#tp").value } });
      closeModal(); render();
    };
  };
};

routes.reports = async (view) => {
  const r = await api("/api/reports");
  view.innerHTML = `<div class="grid two">
    <div class="card"><h3>Нагрузка врачей за 30 дней</h3>
      <table class="table">${r.by_doctor.map((x)=>`<tr><td>${esc(x.name)}<div class="meta">${esc(x.specialty)}</div></td><td>${x.visits} записей</td><td>${x.done} завершено</td></tr>`).join("")}</table>
    </div>
    <div class="card"><h3>Услуги</h3>
      <canvas id="chart-svc" height="160"></canvas>
    </div>
    <div class="card"><h3>Касса по дням</h3>
      <table class="table">${r.cash.map((x)=>`<tr><td>${esc(x.day||"—")}</td><td>${esc(x.method)}</td><td>${money(x.amount)}</td></tr>`).join("") || emptyRow(3)}</table>
    </div>
    <div class="card"><h3>Воронка статусов</h3>
      <canvas id="chart-fun" height="160"></canvas>
    </div>
  </div>`;
  chart("chart-svc", {
    type: "bar",
    data: { labels: r.by_service.map((x) => x.name), datasets: [{ data: r.by_service.map((x) => x.cnt), backgroundColor: "#3d8b4e" }] },
    options: { plugins: { legend: { display: false } }, indexAxis: "y" },
  });
  chart("chart-fun", {
    type: "doughnut",
    data: { labels: r.funnel.map((x) => (STATUS[x.status] || [x.status])[0]), datasets: [{ data: r.funnel.map((x) => x.cnt), backgroundColor: ["#3d8b4e","#2f6fed","#e09a3c","#7c3aed","#94a3b8","#e63946"] }] },
  });
};

routes.structure = async (view) => {
  view.innerHTML = `
    <div class="card">
      <h3>Как устроена CRM клиники</h3>
      <p class="meta">Модель для «Семейный доктор»: регистратура ведёт поток, врач — карту, касса — деньги, склад — расходники. Все роли смотрят одну базу.</p>
      <div class="flow">
        <span>1. Обращение</span><em>→</em><span>2. Запись</span><em>→</em><span>3. Очередь</span><em>→</em>
        <span>4. Приём / ЭМК</span><em>→</em><span>5. Анализы и назначения</span><em>→</em><span>6. Касса</span><em>→</em>
        <span>7. Напоминание</span>
      </div>
    </div>
    <div class="structure" style="margin-top:14px">
      <article><h3>Роли</h3><ul>
        <li>Главный врач — всё + настройки</li>
        <li>Регистратура — картотека, расписание, очередь, счета</li>
        <li>Врач — свои приёмы, ЭМК, назначения, чат</li>
        <li>Медсестра — очередь, анализы, склад</li>
        <li>Касса — счета, оплаты, отчёты</li>
      </ul></article>
      <article><h3>Модули</h3><ul>
        <li>Дашборд KPI и задачи дня</li>
        <li>Недельное расписание и живая очередь</li>
        <li>Картотека и электронная медкарта</li>
        <li>Лаборатория, аптека, касса, склад</li>
        <li>Чат с пациентом и аналитика</li>
      </ul></article>
      <article><h3>Данные</h3><ul>
        <li>Пациент 1—N приёмы, счета, сообщения</li>
        <li>Приём связан с врачом, услугой, кабинетом</li>
        <li>Визит порождает назначения и лаб.заказы</li>
        <li>Счёт состоит из позиций прайса</li>
        <li>Склад контролирует минимум остатка</li>
      </ul></article>
    </div>
    <div class="grid two" style="margin-top:14px">
      <div class="card">
        <h3>Экран врача</h3>
        <ol>
          <li>Открывает очередь → приглашает пациента</li>
          <li>Пишет протокол SOAP / диагноз МКБ-10</li>
          <li>Назначает препарат и анализы</li>
          <li>Отвечает в чате после визита</li>
        </ol>
      </div>
      <div class="card">
        <h3>Экран регистратуры</h3>
        <ol>
          <li>Ищет карту или заводит новую</li>
          <li>Кликает слот в расписании</li>
          <li>Ставит в очередь при явке</li>
          <li>Выставляет счёт и принимает оплату</li>
        </ol>
      </div>
    </div>`;
};

routes.settings = async (view) => {
  const s = state.meta.settings;
  view.innerHTML = `<div class="grid two">
    <div class="card">
      <h3>Клиника</h3>
      <div class="fields">
        <label class="field">Название<input id="clinic_name" value="${esc(s.clinic_name||"")}"></label>
        <label class="field">Телефон<input id="phone" value="${esc(s.phone||"")}"></label>
        <label class="field full">Адрес<input id="address" value="${esc(s.address||"")}"></label>
        <label class="field">С<input id="work_from" value="${esc(s.work_from||"")}"></label>
        <label class="field">До<input id="work_to" value="${esc(s.work_to||"")}"></label>
      </div>
      <div class="modal-actions"><button class="btn primary" id="save-s">Сохранить</button></div>
    </div>
    <div class="card">
      <h3>Прайс</h3>
      <table class="table">${state.meta.services.map((x)=>`<tr><td>${esc(x.name)}</td><td>${esc(x.category)}</td><td>${x.duration_min} мин</td><td>${money(x.price)}</td></tr>`).join("")}</table>
      <button class="btn" id="add-svc" style="margin-top:10px">+ Услуга</button>
    </div>
    <div class="card">
      <h3>Персонал</h3>
      ${state.meta.staff.map((u)=>`<div class="q-item"><div class="ava" style="background:${u.color}">${esc(initials(u.full_name))}</div><div><strong>${esc(u.full_name)}</strong><div class="meta">${esc(roleName(u.role))} · ${esc(u.specialty)}</div></div></div>`).join("")}
    </div>
    <div class="card">
      <h3>Кабинеты</h3>
      ${state.meta.rooms.map((r)=>`<div class="q-item"><strong>${esc(r.name)}</strong><span class="pill gray">${esc(r.kind)}</span></div>`).join("")}
    </div>
  </div>`;
  $("#save-s").onclick = async () => {
    try {
      await api("/api/settings", { method: "PUT", body: {
        clinic_name: $("#clinic_name").value, phone: $("#phone").value, address: $("#address").value,
        work_from: $("#work_from").value, work_to: $("#work_to").value,
      }});
      toast("Сохранено");
      await loadMeta();
    } catch (e) { toast(e.message); }
  };
  $("#add-svc").onclick = () => {
    openModal(`<h3>Услуга</h3><div class="fields">
      <label class="field">Название<input id="sn"></label>
      <label class="field">Категория<input id="sc" value="приём"></label>
      <label class="field">Минуты<input id="sd" type="number" value="30"></label>
      <label class="field">Цена<input id="sp" type="number" value="2000"></label>
    </div><div class="modal-actions"><button class="btn" id="c">Отмена</button><button class="btn primary" id="ok">Добавить</button></div>`);
    $("#c").onclick = closeModal;
    $("#ok").onclick = async () => {
      await api("/api/services", { method: "POST", body: { name: $("#sn").value, category: $("#sc").value, duration_min: $("#sd").value, price: $("#sp").value } });
      await loadMeta(); closeModal(); render();
    };
  };
};

async function formPatient(p = {}) {
  const doctors = state.meta.doctors;
  openModal(`<h3>${p.id ? "Карточка" : "Новый пациент"}</h3>
    <div class="fields">
      <label class="field">Фамилия<input id="last_name" value="${esc(p.last_name||"")}"></label>
      <label class="field">Имя<input id="first_name" value="${esc(p.first_name||"")}"></label>
      <label class="field">Отчество<input id="patronymic" value="${esc(p.patronymic||"")}"></label>
      <label class="field">Дата рождения<input id="birth_date" type="date" value="${esc(p.birth_date||"")}"></label>
      <label class="field">Телефон<input id="phone" value="${esc(p.phone||"")}"></label>
      <label class="field">Пол<select id="sex"><option value="female" ${p.sex==="female"?"selected":""}>женский</option><option value="male" ${p.sex==="male"?"selected":""}>мужской</option></select></label>
      <label class="field">Страховка<input id="insurance" value="${esc(p.insurance||"")}"></label>
      <label class="field">Врач<select id="doctor_id">${optionList(doctors,"id","full_name",p.doctor_id)}</select></label>
      <label class="field full">Аллергии<input id="allergies" value="${esc(p.allergies||"")}"></label>
      <label class="field full">Хронические<input id="chronic" value="${esc(p.chronic||"")}"></label>
    </div>
    <div class="modal-actions"><button class="btn" id="c">Отмена</button><button class="btn primary" id="ok">Сохранить</button></div>`);
  $("#c").onclick = closeModal;
  $("#ok").onclick = async () => {
    const body = Object.fromEntries(["last_name","first_name","patronymic","birth_date","phone","sex","insurance","doctor_id","allergies","chronic"].map((k) => [k, $("#"+k).value]));
    if (p.id) await api("/api/patients/" + p.id, { method: "PUT", body });
    else {
      const created = await api("/api/patients", { method: "POST", body });
      closeModal(); go("patient/" + created.id); return;
    }
    closeModal(); render();
  };
}

async function formAppointment(pre = {}) {
  const patients = await api("/api/patients");
  openModal(`<h3>Запись на приём</h3>
    <div class="fields">
      <label class="field">Пациент<select id="patient_id">${patientOptions(patients, pre.patient_id)}</select></label>
      <label class="field">Врач<select id="doctor_id">${optionList(state.meta.doctors,"id","full_name",pre.doctor_id || state.user.id)}</select></label>
      <label class="field">Услуга<select id="service_id">${optionList(state.meta.services,"id","name",pre.service_id)}</select></label>
      <label class="field">Кабинет<select id="room_id">${optionList(state.meta.rooms,"id","name",pre.room_id)}</select></label>
      <label class="field">Начало<input id="start_at" type="datetime-local" value="${esc((pre.start_at||"").replace(" ","T").slice(0,16))}"></label>
      <label class="field">Жалоба<input id="complaint" value="${esc(pre.complaint||"")}"></label>
      <label class="field full"><input type="checkbox" id="create_invoice" checked /> Сразу выставить счёт</label>
    </div>
    <div class="modal-actions"><button class="btn" id="c">Отмена</button><button class="btn primary" id="ok">Записать</button></div>`);
  $("#c").onclick = closeModal;
  $("#ok").onclick = async () => {
    const start = $("#start_at").value.replace("T", " ") + ":00";
    await api("/api/appointments", { method: "POST", body: {
      patient_id: $("#patient_id").value, doctor_id: $("#doctor_id").value, service_id: $("#service_id").value,
      room_id: $("#room_id").value, start_at: start, complaint: $("#complaint").value, create_invoice: $("#create_invoice").checked,
    }});
    closeModal(); toast("Пациент записан"); render();
  };
}

function formVisit(v = {}, edit = false) {
  openModal(`<h3>Протокол приёма</h3>
    <div class="fields">
      <label class="field full">Жалобы<textarea id="complaint">${esc(v.complaint||"")}</textarea></label>
      <label class="field full">Анамнез<textarea id="anamnesis">${esc(v.anamnesis||"")}</textarea></label>
      <label class="field full">Осмотр<textarea id="examination">${esc(v.examination||"")}</textarea></label>
      <label class="field">Диагноз<input id="diagnosis" value="${esc(v.diagnosis||"")}"></label>
      <label class="field">МКБ-10<input id="icd10" value="${esc(v.icd10||"")}"></label>
      <label class="field full">Рекомендации<textarea id="recommendations">${esc(v.recommendations||"")}</textarea></label>
    </div>
    <div class="modal-actions"><button class="btn" id="c">Отмена</button><button class="btn primary" id="ok">Сохранить</button></div>`);
  $("#c").onclick = closeModal;
  $("#ok").onclick = async () => {
    const body = Object.fromEntries(["complaint","anamnesis","examination","diagnosis","icd10","recommendations"].map((k)=>[k,$("#"+k).value]));
    if (edit) await api("/api/visits/" + v.id, { method: "PUT", body });
    else await api("/api/visits", { method: "POST", body: { ...body, patient_id: v.patient_id, doctor_id: v.doctor_id, appointment_id: v.appointment_id } });
    closeModal(); render();
  };
}

async function formLab(pre = {}) {
  const patients = await api("/api/patients");
  openModal(`<h3>Заказ анализа</h3><div class="fields">
    <label class="field">Пациент<select id="patient_id">${patientOptions(patients, pre.patient_id)}</select></label>
    <label class="field">Исследование<input id="test_name" value="Общий анализ крови"></label>
    <label class="field full">Комментарий<input id="comment"></label>
  </div><div class="modal-actions"><button class="btn" id="c">Отмена</button><button class="btn primary" id="ok">Назначить</button></div>`);
  $("#c").onclick = closeModal;
  $("#ok").onclick = async () => {
    await api("/api/lab", { method: "POST", body: { patient_id: $("#patient_id").value, test_name: $("#test_name").value, comment: $("#comment").value } });
    closeModal(); render();
  };
}

async function formRx(pre = {}) {
  openModal(`<h3>Назначение</h3><div class="fields">
    <label class="field">Препарат<input id="medication"></label>
    <label class="field">Дозировка<input id="dosage" placeholder="10 мг утром"></label>
    <label class="field">Дней<input id="duration_days" type="number" value="14"></label>
    <label class="field">Раз в день<input id="times_per_day" type="number" value="1"></label>
    <label class="field full">Инструкция<input id="instructions"></label>
  </div><div class="modal-actions"><button class="btn" id="c">Отмена</button><button class="btn primary" id="ok">Назначить</button></div>`);
  $("#c").onclick = closeModal;
  $("#ok").onclick = async () => {
    await api("/api/prescriptions", { method: "POST", body: {
      patient_id: pre.patient_id, medication: $("#medication").value, dosage: $("#dosage").value,
      duration_days: $("#duration_days").value, times_per_day: $("#times_per_day").value, instructions: $("#instructions").value,
    }});
    closeModal(); render();
  };
}

async function formInvoice() {
  const patients = await api("/api/patients");
  openModal(`<h3>Новый счёт</h3><div class="fields">
    <label class="field full">Пациент<select id="patient_id">${patientOptions(patients)}</select></label>
    <label class="field full">Услуга<select id="service_id">${optionList(state.meta.services,"id","name")}</select></label>
  </div><div class="modal-actions"><button class="btn" id="c">Отмена</button><button class="btn primary" id="ok">Выставить</button></div>`);
  $("#c").onclick = closeModal;
  $("#ok").onclick = async () => {
    const svc = state.meta.services.find((s) => String(s.id) === $("#service_id").value);
    await api("/api/invoices", { method: "POST", body: {
      patient_id: $("#patient_id").value,
      items: [{ service_id: svc.id, title: svc.name, qty: 1, price: svc.price }],
    }});
    closeModal(); render();
  };
}

boot();
