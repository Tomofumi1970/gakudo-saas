/* eslint-disable */
(function () {
  const cfg = window.GAKUDO_CONFIG;
  const { CognitoUserPool, CognitoUser, AuthenticationDetails } =
    window.AmazonCognitoIdentity;
  const pool = new CognitoUserPool({
    UserPoolId: cfg.userPoolId,
    ClientId: cfg.userPoolClientId,
  });

  const $ = (sel, root) => (root || document).querySelector(sel);
  const h = (tag, attrs, ...children) => {
    const el = document.createElement(tag);
    if (attrs) {
      for (const [k, v] of Object.entries(attrs)) {
        if (k === 'class') el.className = v;
        else if (k === 'onclick') el.onclick = v;
        else if (k === 'html') el.innerHTML = v;
        else el.setAttribute(k, v);
      }
    }
    for (const c of children.flat()) {
      if (c == null) continue;
      el.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
    }
    return el;
  };

  const state = {
    session: null, // CognitoUserSession
    claims: null,
    activeTab: 'household',
  };

  /* ============ Auth ============ */

  function currentSession() {
    return new Promise((resolve) => {
      const u = pool.getCurrentUser();
      if (!u) return resolve(null);
      u.getSession((err, session) => {
        if (err || !session || !session.isValid()) return resolve(null);
        resolve({ user: u, session });
      });
    });
  }

  function signIn(username, password) {
    return new Promise((resolve, reject) => {
      const user = new CognitoUser({ Username: username, Pool: pool });
      const auth = new AuthenticationDetails({ Username: username, Password: password });
      user.authenticateUser(auth, {
        onSuccess: (session) => resolve({ user, session }),
        onFailure: (err) => reject(err),
        newPasswordRequired: (attrs) => {
          // 初回ログイン時の新パスワード要求
          const newPw = prompt('新しいパスワードを設定してください(10文字以上、大小英数字を含む):');
          if (!newPw) return reject(new Error('cancelled'));
          delete attrs.email_verified;
          user.completeNewPasswordChallenge(newPw, {}, {
            onSuccess: (session) => resolve({ user, session }),
            onFailure: (err) => reject(err),
          });
        },
      });
    });
  }

  function signOut() {
    const u = pool.getCurrentUser();
    if (u) u.signOut();
    state.session = null;
    state.claims = null;
    render();
  }

  function parseClaims(session) {
    return session.getIdToken().payload;
  }

  /* ============ API ============ */

  async function api(method, path, body) {
    const token = state.session.getIdToken().getJwtToken();
    const url = cfg.apiUrl.replace(/\/+$/, '') + path;
    const res = await fetch(url, {
      method,
      headers: {
        Authorization: token,
        'Content-Type': 'application/json',
      },
      body: body ? JSON.stringify(body) : undefined,
    });
    const text = await res.text();
    let data;
    try { data = JSON.parse(text); } catch { data = { raw: text }; }
    if (!res.ok) {
      const err = new Error(data.error || res.statusText);
      err.status = res.status;
      err.body = data;
      throw err;
    }
    return data;
  }

  /* ============ Views ============ */

  function loginView() {
    const box = h('div', { class: 'login-box' },
      h('h2', null, '学童SaaS ログイン'),
      h('label', null, 'メールアドレス'),
      h('input', { id: 'email', type: 'email', autocomplete: 'username' }),
      h('label', null, 'パスワード'),
      h('input', { id: 'password', type: 'password', autocomplete: 'current-password' }),
      h('div', { style: 'margin-top: 1.5rem;' },
        h('button', {
          class: 'primary', style: 'width: 100%;',
          onclick: async () => {
            const email = $('#email').value.trim();
            const pw = $('#password').value;
            $('#login-error').textContent = '';
            try {
              const { session } = await signIn(email, pw);
              state.session = session;
              state.claims = parseClaims(session);
              render();
            } catch (e) {
              $('#login-error').textContent = e.message || String(e);
            }
          },
        }, 'ログイン'),
      ),
      h('div', { id: 'login-error', class: 'error' }),
      h('p', { style: 'margin-top: 1rem; font-size: 0.8rem; color: #57606a;' },
        '初回ログイン時は仮パスワードでログイン後、新パスワード設定を求められます。'),
    );
    return box;
  }

  /* --- 共通レンダー: テーブル --- */
  function tableOf(items, columns, emptyText) {
    if (!items || items.length === 0) {
      return h('div', { class: 'empty' }, emptyText || '(データなし)');
    }
    const thead = h('thead', null, h('tr', null,
      columns.map((c) => h('th', null, c.label)),
    ));
    const tbody = h('tbody', null,
      items.map((row) => h('tr', null,
        columns.map((c) => h('td', { html: c.render ? c.render(row) : (row[c.key] ?? '') })),
      )),
    );
    return h('table', null, thead, tbody);
  }

  /* --- 自世帯タブ --- */
  async function renderHousehold(panel) {
    panel.appendChild(h('h2', null, '自世帯'));
    try {
      const r = await api('GET', '/me/household');
      panel.appendChild(h('p', null, `住所: ${r.household.address}`));
      panel.appendChild(tableOf(r.members, [
        { label: '区分', key: 'member_type' },
        { label: 'ステータス', key: 'status' },
        { label: '姓', key: 'family_name' },
        { label: '名', key: 'given_name' },
        { label: '学年', render: (m) => m.grade || '-' },
        { label: 'アレルギー', render: (m) => m.allergies || '-' },
      ], '世帯メンバーがありません'));
    } catch (e) {
      panel.appendChild(h('div', { class: 'error' }, e.message));
    }
  }

  /* --- 請求書タブ --- */
  async function renderInvoices(panel) {
    panel.appendChild(h('h2', null, '請求書'));
    try {
      const isParent = state.claims['custom:user_type'] === 'parent';
      const r = isParent
        ? await api('GET', '/me/invoices')
        : await api('GET', '/households');
      if (isParent) {
        panel.appendChild(tableOf(r.items, [
          { label: '請求対象', key: 'billing_unit' },
          { label: '合計', render: (i) => '¥' + Number(i.total).toLocaleString() },
          { label: '明細数', key: 'line_count' },
          { label: 'ステータス', render: (i) => `<span class="badge ${(i.status||'').toLowerCase()}">${i.status}</span>` },
        ], '請求書がありません'));
      } else {
        panel.appendChild(h('p', { class: 'info' }, '世帯一覧から個別の請求書を見るには、世帯IDをコピーして使ってください。'));
        panel.appendChild(tableOf(r.items, [
          { label: '住所', key: 'address' },
          { label: 'TEL', key: 'phone' },
          { label: 'household_id', render: (h) => `<code style="font-size:0.75em">${h.household_id}</code>` },
        ], '世帯がありません'));
      }
    } catch (e) {
      panel.appendChild(h('div', { class: 'error' }, e.message));
    }
  }

  /* --- お知らせタブ --- */
  async function renderAnnouncements(panel) {
    panel.appendChild(h('h2', null, 'お知らせ'));
    try {
      const r = await api('GET', '/me/announcements');
      panel.appendChild(tableOf(r.items, [
        { label: '種別', key: 'type' },
        { label: 'タイトル', key: 'title' },
        { label: '本文', render: (a) => (a.body || '').replace(/\n/g, '<br>') },
        { label: '配信日時', key: 'sent_at' },
      ], 'お知らせがありません'));
    } catch (e) {
      panel.appendChild(h('div', { class: 'error' }, e.message));
    }
  }

  /* --- スタッフ: お知らせ作成 --- */
  function renderAnnouncementsCreate(panel) {
    panel.appendChild(h('h2', null, 'お知らせ作成・配信'));
    const form = h('div', { class: 'row' },
      h('div', null,
        h('label', null, '種別'),
        h('select', { id: 'a-type' },
          h('option', { value: 'GENERAL' }, '一般'),
          h('option', { value: 'SCHOOL_CLOSURE' }, '学級閉鎖'),
          h('option', { value: 'WEATHER_WARNING' }, '気象警報'),
          h('option', { value: 'EVENT_INVITE' }, '行事案内'),
        ),
      ),
      h('div', null,
        h('label', null, '対象'),
        h('select', { id: 'a-aud' }, h('option', { value: 'ALL' }, '全保護者')),
      ),
    );
    panel.appendChild(form);
    panel.appendChild(h('label', null, 'タイトル'));
    panel.appendChild(h('input', { id: 'a-title' }));
    panel.appendChild(h('label', null, '本文'));
    panel.appendChild(h('textarea', { id: 'a-body', rows: 5 }));
    panel.appendChild(h('div', { style: 'margin-top: 1rem; display: flex; gap: 0.5rem;' },
      h('button', {
        class: 'primary',
        onclick: async () => {
          try {
            const created = await api('POST', '/announcements', {
              title: $('#a-title').value,
              body: $('#a-body').value,
              type: $('#a-type').value,
              target_audience: $('#a-aud').value,
            });
            const sent = await api('POST', `/announcements/${created.announcement_id}/send`, {});
            $('#a-result').innerHTML = `配信完了: recipient_count=${sent.recipient_count}, failed_count=${sent.failed_count}`;
          } catch (e) {
            $('#a-result').innerHTML = `<span class="error">${e.message}</span>`;
          }
        },
      }, '作成 + 即時配信'),
    ));
    panel.appendChild(h('div', { id: 'a-result', class: 'info', style: 'margin-top:0.5rem' }));
  }

  /* --- スタッフ: 出席記録 --- */
  function renderAttendance(panel) {
    panel.appendChild(h('h2', null, '出席記録'));
    panel.appendChild(h('label', null, '日付'));
    panel.appendChild(h('input', { id: 'att-date', type: 'date' }));
    panel.appendChild(h('div', { style: 'margin-top: 0.5rem;' },
      h('button', { class: 'primary', onclick: async () => {
        const date = $('#att-date').value;
        if (!date) return;
        const r = await api('GET', `/attendance?date=${date}`);
        const wrap = $('#att-result'); wrap.innerHTML = '';
        wrap.appendChild(tableOf(r.items, [
          { label: 'member_id', render: (i) => i.member_id.slice(0,8)+'..' },
          { label: 'status', key: 'status' },
          { label: '登所', render: (i) => i.arrival_time || '-' },
          { label: '退所', render: (i) => i.departure_time || '-' },
        ], 'この日の記録はありません'));
      }}, '取得'),
    ));
    panel.appendChild(h('div', { id: 'att-result', style: 'margin-top:1rem' }));
  }

  /* --- 議事録タブ --- */
  async function renderMeetings(panel) {
    panel.appendChild(h('h2', null, '議事録'));
    try {
      const isParent = state.claims['custom:user_type'] === 'parent';
      const r = await api('GET', isParent ? '/me/meetings' : '/meetings');
      panel.appendChild(tableOf(r.items, [
        { label: '日付', key: 'meeting_date' },
        { label: '種別', key: 'meeting_type' },
        { label: 'タイトル', key: 'title' },
        { label: '議題', render: (m) => (m.agenda || '').slice(0, 60) },
        { label: 'AI要約', render: (m) => Array.isArray(m.ai_summary) ? m.ai_summary.map(l => `<div>${l}</div>`).join('') : '-' },
        { label: 'AIタグ', render: (m) => Array.isArray(m.ai_tags) ? m.ai_tags.map(t => `<span class="badge">${t}</span>`).join(' ') : '-' },
        { label: 'ステータス', render: (m) => `<span class="badge ${(m.status||'').toLowerCase()}">${m.status}</span>` },
        ...(isParent ? [] : [{
          label: '操作',
          render: (m) => [
            m.status === 'PUBLISHED' ? '' : `<button class="ghost" onclick="window.__publishMinute('${m.minute_id}')">公開</button>`,
            `<button class="ghost" onclick="window.__summarizeMinute('${m.minute_id}', this)">AI要約</button>`,
          ].join(' '),
        }]),
      ], '議事録がありません'));
    } catch (e) {
      panel.appendChild(h('div', { class: 'error' }, e.message));
    }
  }
  window.__publishMinute = async (id) => {
    try { await api('POST', `/meetings/${encodeURIComponent(id)}/publish`, {}); render(); }
    catch (e) { alert(e.message); }
  };
  window.__summarizeMinute = async (id, btn) => {
    btn.textContent = 'AI処理中...'; btn.disabled = true;
    try { await api('POST', `/meetings/${encodeURIComponent(id)}/summarize`, {}); render(); }
    catch (e) { alert(e.message); btn.textContent = 'AI要約'; btn.disabled = false; }
  };

  /* --- スタッフ: 議事録作成 --- */
  function renderMeetingCreate(panel) {
    panel.appendChild(h('h2', null, '議事録作成'));
    panel.appendChild(h('div', { class: 'row' },
      h('div', null,
        h('label', null, '種別'),
        h('select', { id: 'm-type' },
          h('option', { value: 'EXAMPLE' }, '例会'),
          h('option', { value: 'OFFICERS_MEETING' }, '役員会'),
          h('option', { value: 'RUNNING_COMMITTEE' }, '運営委員会'),
          h('option', { value: 'GENERAL_ASSEMBLY' }, '総会'),
        ),
      ),
      h('div', null,
        h('label', null, '開催日'),
        h('input', { id: 'm-date', type: 'date' }),
      ),
    ));
    panel.appendChild(h('label', null, 'タイトル'));
    panel.appendChild(h('input', { id: 'm-title' }));
    panel.appendChild(h('label', null, '議題'));
    panel.appendChild(h('textarea', { id: 'm-agenda', rows: 3 }));
    panel.appendChild(h('label', null, '決定事項'));
    panel.appendChild(h('textarea', { id: 'm-decisions', rows: 3 }));
    panel.appendChild(h('label', null, '本文(詳細)'));
    panel.appendChild(h('textarea', { id: 'm-body', rows: 5 }));
    panel.appendChild(h('div', { style: 'margin-top: 1rem;' },
      h('button', { class: 'primary', onclick: async () => {
        try {
          const r = await api('POST', '/meetings', {
            meeting_type: $('#m-type').value,
            meeting_date: $('#m-date').value,
            title: $('#m-title').value,
            agenda: $('#m-agenda').value,
            decisions: $('#m-decisions').value,
            body: $('#m-body').value,
          });
          $('#m-result').innerHTML = `作成完了 (DRAFT): ${r.minute_id}`;
        } catch (e) { $('#m-result').innerHTML = `<span class="error">${e.message}</span>`; }
      }}, '作成 (DRAFT)'),
    ));
    panel.appendChild(h('div', { id: 'm-result', class: 'info', style: 'margin-top:0.5rem' }));
  }

  /* --- 規程文書タブ --- */
  async function renderDocuments(panel) {
    panel.appendChild(h('h2', null, '規程文書(最新版)'));
    try {
      const r = await api('GET', '/documents');
      const items = r.items;
      if (!items.length) {
        panel.appendChild(h('div', { class: 'empty' }, '規程文書がありません'));
      } else {
        panel.appendChild(tableOf(items, [
          { label: 'doc_key', key: 'doc_key' },
          { label: '種別', key: 'doc_type' },
          { label: 'タイトル', key: 'title' },
          { label: 'version', render: (d) => `<code style="font-size:0.75em">${d.version}</code>` },
          { label: '適用日', render: (d) => d.effective_from || '-' },
          { label: '操作', render: (d) => `<button class="ghost" onclick="window.__downloadDoc('${d.doc_key}','${d.version}')">DL</button>` },
        ], '規程文書がありません'));
      }
    } catch (e) { panel.appendChild(h('div', { class: 'error' }, e.message)); }
  }
  window.__downloadDoc = async (docKey, version) => {
    try {
      const r = await api('GET', `/documents/${encodeURIComponent(docKey)}/download-url?version=${encodeURIComponent(version)}`);
      window.open(r.download_url, '_blank');
    } catch (e) { alert(e.message); }
  };

  /* --- スタッフ: 規程アップロード --- */
  function renderDocsUpload(panel) {
    panel.appendChild(h('h2', null, '規程文書 アップロード'));
    panel.appendChild(h('div', { class: 'row' },
      h('div', null,
        h('label', null, 'doc_key (英小文字+_)'),
        h('input', { id: 'd-key', placeholder: 'employment_rules' }),
      ),
      h('div', null,
        h('label', null, '種別'),
        h('select', { id: 'd-type' },
          h('option', { value: 'EMPLOYMENT_RULES' }, '就業規則'),
          h('option', { value: 'WAGE_RULES' }, '賃金規程'),
          h('option', { value: 'OPERATION_RULES' }, '運営規程'),
          h('option', { value: 'BYLAWS' }, '基本規約'),
          h('option', { value: 'CONTRACT' }, '契約書'),
          h('option', { value: 'OTHER' }, 'その他'),
        ),
      ),
    ));
    panel.appendChild(h('label', null, 'タイトル'));
    panel.appendChild(h('input', { id: 'd-title' }));
    panel.appendChild(h('label', null, '説明(任意)'));
    panel.appendChild(h('textarea', { id: 'd-desc', rows: 2 }));
    panel.appendChild(h('label', null, '適用開始日(任意)'));
    panel.appendChild(h('input', { id: 'd-eff', type: 'date' }));
    panel.appendChild(h('label', null, 'ファイル'));
    panel.appendChild(h('input', { id: 'd-file', type: 'file' }));
    panel.appendChild(h('div', { style: 'margin-top:1rem' },
      h('button', { class: 'primary', onclick: async () => {
        const file = $('#d-file').files[0];
        if (!file) { $('#d-result').textContent = 'ファイル未選択'; return; }
        const docKey = $('#d-key').value.trim();
        const docType = $('#d-type').value;
        const title = $('#d-title').value.trim();
        if (!docKey || !title) { $('#d-result').textContent = 'doc_key と title は必須'; return; }
        $('#d-result').innerHTML = 'アップロードURL取得中...';
        try {
          const up = await api('POST', '/documents/upload-url', {
            doc_key: docKey,
            filename: file.name,
            mime_type: file.type || 'application/octet-stream',
          });
          $('#d-result').innerHTML = 'S3へアップロード中...';
          const r2 = await fetch(up.upload_url, {
            method: 'PUT', headers: { 'Content-Type': file.type || 'application/octet-stream' }, body: file,
          });
          if (!r2.ok) throw new Error('S3 PUT failed: ' + r2.status);
          $('#d-result').innerHTML = 'メタデータ登録中...';
          const reg = await api('POST', '/documents', {
            doc_key: docKey,
            doc_type: docType,
            title,
            description: $('#d-desc').value,
            effective_from: $('#d-eff').value,
            s3_key: up.s3_key,
            version_stamp: up.version_stamp,
            mime_type: file.type, file_size: file.size,
          });
          $('#d-result').innerHTML = `登録完了 version=${reg.version}`;
        } catch (e) { $('#d-result').innerHTML = `<span class="error">${e.message}</span>`; }
      }}, 'アップロード + 登録(旧版を自動SUPERSEDE)'),
    ));
    panel.appendChild(h('div', { id: 'd-result', class: 'info', style: 'margin-top:0.5rem' }));
  }

  /* --- 総会議決タブ(保護者は投票、スタッフは結果集計) --- */
  async function renderResolutions(panel) {
    panel.appendChild(h('h2', null, '総会議決'));
    try {
      const r = await api('GET', '/resolutions');
      if (!r.items.length) {
        panel.appendChild(h('div', { class: 'empty' }, '議案はありません'));
        return;
      }
      for (const res of r.items) {
        const tallyBtn = h('button', { class: 'ghost', onclick: async () => {
          try {
            const t = await api('GET', `/resolutions/${encodeURIComponent(res.resolution_id)}/tally`);
            const wrap = document.getElementById(`tally-${res.resolution_id}`);
            wrap.innerHTML = `<strong>集計:</strong> ${Object.entries(t.tally).map(([k,v])=>`${k}=${v}`).join(' / ')} (票数 ${t.tally_total}, 委任 ${t.proxy_count} 中 ${t.proxy_transferred} 反映)`;
          } catch (e) { alert(e.message); }
        }}, '集計');
        const card = h('section', { style: 'border:1px solid #d0d7de; border-radius:6px; padding:1rem; margin-bottom:1rem' },
          h('div', null, h('strong', null, `${res.order_no}. ${res.title}`), ' ', h('span', { class: 'badge' }, res.status)),
          h('div', { class: 'info', style: 'font-size: 0.85rem' }, `assembly=${res.assembly_id} options=${res.options.join('/')}`),
          res.body ? h('p', null, res.body) : null,
          h('div', null,
            ...res.options.map(opt => h('button', { class: 'ghost', style: 'margin-right:0.5rem', onclick: async () => {
              try { await api('POST', `/resolutions/${encodeURIComponent(res.resolution_id)}/votes`, { choice: opt }); alert(`投票: ${opt}`); }
              catch (e) { alert(e.message); }
            }}, opt)),
            tallyBtn,
          ),
          h('div', { id: `tally-${res.resolution_id}`, style: 'margin-top:0.5rem; color:#0969da' }),
        );
        panel.appendChild(card);
      }
    } catch (e) {
      panel.appendChild(h('div', { class: 'error' }, e.message));
    }
  }

  /* --- スタッフ: 議案作成 --- */
  function renderResolutionCreate(panel) {
    panel.appendChild(h('h2', null, '議案作成'));
    panel.appendChild(h('div', { class: 'row' },
      h('div', null,
        h('label', null, 'assembly_id (例: GA2026)'),
        h('input', { id: 'r-asm' }),
      ),
      h('div', null,
        h('label', null, 'order_no (例: 01)'),
        h('input', { id: 'r-ord' }),
      ),
    ));
    panel.appendChild(h('label', null, 'タイトル'));
    panel.appendChild(h('input', { id: 'r-title' }));
    panel.appendChild(h('label', null, '本文(任意)'));
    panel.appendChild(h('textarea', { id: 'r-body', rows: 4 }));
    panel.appendChild(h('label', null, '選択肢(カンマ区切り、既定: yes,no,abstain)'));
    panel.appendChild(h('input', { id: 'r-opts', placeholder: 'yes,no,abstain' }));
    panel.appendChild(h('div', { style: 'margin-top:1rem' },
      h('button', { class: 'primary', onclick: async () => {
        try {
          const optsStr = $('#r-opts').value.trim();
          const r = await api('POST', '/resolutions', {
            assembly_id: $('#r-asm').value,
            order_no: $('#r-ord').value,
            title: $('#r-title').value,
            body: $('#r-body').value,
            options: optsStr ? optsStr.split(',').map(s => s.trim()) : undefined,
          });
          $('#r-result').textContent = '作成: ' + r.resolution_id;
        } catch (e) { $('#r-result').innerHTML = `<span class="error">${e.message}</span>`; }
      }}, '議案作成'),
    ));
    panel.appendChild(h('div', { id: 'r-result', class: 'info', style: 'margin-top:0.5rem' }));
  }

  /* --- スタッフ: 世帯マスタ(全世帯+メンバー編集) --- */
  async function renderHouseholdMaster(panel) {
    panel.appendChild(h('h2', null, '世帯マスタ'));
    panel.appendChild(h('p', { class: 'info' }, 'スタッフは自施設の全世帯と全メンバーを閲覧・編集できます。'));

    try {
      const houses = await api('GET', '/households');
      if (!houses.items.length) {
        panel.appendChild(h('div', { class: 'empty' }, '世帯がありません。'));
      }

      for (const house of houses.items) {
        const card = h('section', { style: 'border:1px solid #d0d7de; border-radius:6px; padding:1rem; margin-bottom:1rem' });
        const headerRow = h('div', { style: 'display:flex; justify-content:space-between; align-items:center' },
          h('div', null, h('strong', null, house.address || '(住所未登録)'), ' ', h('span', { class: 'info', style: 'font-size:0.8rem' }, `TEL: ${house.phone || '-'} | id=${house.household_id.slice(0,8)}..`)),
          h('div', null,
            h('button', { class: 'ghost', onclick: () => window.__editHousehold(house.household_id) }, '世帯編集'),
            ' ',
            h('button', { class: 'ghost', onclick: () => window.__toggleMembers(house.household_id) }, 'メンバー表示'),
          ),
        );
        card.appendChild(headerRow);
        card.appendChild(h('div', { id: `hh-edit-${house.household_id}` }));
        card.appendChild(h('div', { id: `hh-members-${house.household_id}` }));
        panel.appendChild(card);
      }
    } catch (e) {
      panel.appendChild(h('div', { class: 'error' }, e.message));
    }
  }

  window.__editHousehold = (hid) => {
    const wrap = document.getElementById(`hh-edit-${hid}`);
    if (wrap.innerHTML) { wrap.innerHTML = ''; return; }
    wrap.innerHTML = '';
    api('GET', '/households').then(r => {
      const ho = r.items.find(x => x.household_id === hid);
      const form = h('div', { style: 'margin-top:1rem; padding:1rem; background:#f6f8fa; border-radius:4px' },
        h('label', null, '住所'),
        h('input', { id: `eh-addr-${hid}`, value: ho.address || '' }),
        h('label', null, 'TEL'),
        h('input', { id: `eh-phone-${hid}`, value: ho.phone || '' }),
        h('label', null, 'メモ'),
        h('input', { id: `eh-note-${hid}`, value: ho.note || '' }),
        h('div', { style: 'margin-top:0.5rem' },
          h('button', { class: 'primary', onclick: async () => {
            try {
              await api('PATCH', `/households/${encodeURIComponent(hid)}`, {
                address: document.getElementById(`eh-addr-${hid}`).value,
                phone: document.getElementById(`eh-phone-${hid}`).value,
                note: document.getElementById(`eh-note-${hid}`).value,
              });
              alert('世帯を更新しました'); render();
            } catch (e) { alert(e.message); }
          }}, '保存'),
        ),
      );
      wrap.appendChild(form);
    });
  };

  window.__toggleMembers = async (hid) => {
    const wrap = document.getElementById(`hh-members-${hid}`);
    if (wrap.innerHTML) { wrap.innerHTML = ''; return; }
    try {
      const r = await api('GET', `/households/${encodeURIComponent(hid)}/members`);
      wrap.appendChild(h('h3', { style: 'margin-top:1rem' }, `メンバー (${r.count}人)`));
      if (!r.items.length) wrap.appendChild(h('div', { class: 'empty' }, 'メンバー未登録'));
      else wrap.appendChild(tableOf(r.items, [
        { label: '区分', key: 'member_type' },
        { label: 'ステータス', key: 'status' },
        { label: '姓', key: 'family_name' },
        { label: '名', key: 'given_name' },
        { label: '学年', render: (m) => m.grade || '-' },
        { label: 'メール', render: (m) => m.email || '-' },
        { label: 'TEL', render: (m) => m.phone || '-' },
        { label: '操作', render: (m) => `<button class="ghost" onclick="window.__editMember('${m.member_id}', '${hid}')">編集</button>` },
      ], ''));
      // 新規メンバー追加フォーム
      wrap.appendChild(h('h3', { style: 'margin-top:1rem' }, 'メンバー追加'));
      wrap.appendChild(h('div', { class: 'row' },
        h('div', null,
          h('label', null, '区分'),
          h('select', { id: `am-type-${hid}` },
            h('option', { value: 'child' }, '児童'),
            h('option', { value: 'guardian' }, '保護者'),
            h('option', { value: 'sibling' }, '兄弟'),
            h('option', { value: 'contact' }, '緊急連絡先'),
          ),
        ),
        h('div', null,
          h('label', null, 'ステータス'),
          h('select', { id: `am-status-${hid}` },
            ['ACTIVE','PROSPECTIVE','GRADUATED','WITHDRAWN','PRESCHOOL_GUEST','ALUMNI_GUEST','PRIMARY_GUARDIAN','SECONDARY_GUARDIAN','EMERGENCY_CONTACT']
              .map(s => h('option', { value: s }, s)),
          ),
        ),
      ));
      wrap.appendChild(h('div', { class: 'row' },
        h('div', null, h('label', null, '姓'), h('input', { id: `am-fn-${hid}` })),
        h('div', null, h('label', null, '名'), h('input', { id: `am-gn-${hid}` })),
      ));
      wrap.appendChild(h('div', { class: 'row' },
        h('div', null, h('label', null, '学年(児童のみ)'), h('input', { id: `am-grade-${hid}` })),
        h('div', null, h('label', null, 'メール'), h('input', { id: `am-email-${hid}` })),
      ));
      wrap.appendChild(h('label', null, 'アレルギー・配慮事項'));
      wrap.appendChild(h('input', { id: `am-aller-${hid}` }));
      wrap.appendChild(h('div', { style: 'margin-top:0.5rem' },
        h('button', { class: 'primary', onclick: async () => {
          try {
            await api('POST', `/households/${encodeURIComponent(hid)}/members`, {
              member_type: document.getElementById(`am-type-${hid}`).value,
              status: document.getElementById(`am-status-${hid}`).value,
              family_name: document.getElementById(`am-fn-${hid}`).value,
              given_name: document.getElementById(`am-gn-${hid}`).value,
              grade: document.getElementById(`am-grade-${hid}`).value,
              email: document.getElementById(`am-email-${hid}`).value,
              allergies: document.getElementById(`am-aller-${hid}`).value,
            });
            window.__toggleMembers(hid); // 一度閉じて
            window.__toggleMembers(hid); // 再表示
          } catch (e) { alert(e.message); }
        }}, '追加'),
      ));
    } catch (e) {
      wrap.appendChild(h('div', { class: 'error' }, e.message));
    }
  };

  window.__editMember = async (mid, hid) => {
    try {
      const m = await api('GET', `/members/${encodeURIComponent(mid)}`);
      const dlg = h('section', { style: 'position:fixed; top:5%; left:50%; transform:translateX(-50%); background:white; border:1px solid #d0d7de; padding:1.5rem; border-radius:6px; max-width:600px; width:90%; box-shadow:0 4px 20px rgba(0,0,0,0.15); z-index:1000' },
        h('h3', null, `${m.family_name} ${m.given_name} を編集`),
        h('label', null, '姓'),
        h('input', { id: 'em-fn', value: m.family_name || '' }),
        h('label', null, '名'),
        h('input', { id: 'em-gn', value: m.given_name || '' }),
        h('label', null, 'ステータス'),
        h('select', { id: 'em-status' },
          ['ACTIVE','PROSPECTIVE','GRADUATED','WITHDRAWN','PRESCHOOL_GUEST','ALUMNI_GUEST','PRIMARY_GUARDIAN','SECONDARY_GUARDIAN','EMERGENCY_CONTACT']
            .map(s => h('option', { value: s, selected: m.status === s ? 'selected' : null }, s)),
        ),
        h('label', null, '学年(空でクリア)'),
        h('input', { id: 'em-grade', value: m.grade || '' }),
        h('label', null, 'メール'),
        h('input', { id: 'em-email', value: m.email || '' }),
        h('label', null, 'TEL'),
        h('input', { id: 'em-phone', value: m.phone || '' }),
        h('label', null, 'アレルギー'),
        h('input', { id: 'em-aller', value: m.allergies || '' }),
        h('label', null, '配慮事項'),
        h('input', { id: 'em-cons', value: m.considerations || '' }),
        h('div', { style: 'margin-top:1rem; display:flex; gap:0.5rem' },
          h('button', { class: 'primary', onclick: async () => {
            try {
              await api('PATCH', `/members/${encodeURIComponent(mid)}`, {
                family_name: document.getElementById('em-fn').value,
                given_name: document.getElementById('em-gn').value,
                status: document.getElementById('em-status').value,
                grade: document.getElementById('em-grade').value,
                email: document.getElementById('em-email').value,
                phone: document.getElementById('em-phone').value,
                allergies: document.getElementById('em-aller').value,
                considerations: document.getElementById('em-cons').value,
              });
              dlg.remove();
              alert('保存しました'); render();
            } catch (e) { alert(e.message); }
          }}, '保存'),
          h('button', { class: 'ghost', onclick: () => dlg.remove() }, 'キャンセル'),
        ),
      );
      document.body.appendChild(dlg);
    } catch (e) { alert(e.message); }
  };

  /* --- スタッフ: 料金カタログ + 課金登録 + 月次請求生成 --- */
  async function renderBilling(panel) {
    panel.appendChild(h('h2', null, '料金カタログ'));
    try {
      const cat = await api('GET', '/catalog/items');
      const catalog = cat.items.sort((a,b) => (a.billing_unit_type+a.name).localeCompare(b.billing_unit_type+b.name));
      panel.appendChild(tableOf(catalog, [
        { label: '単位', key: 'billing_unit_type' },
        { label: '分類', key: 'category' },
        { label: '品目', key: 'name' },
        { label: '単価', render: (i) => '¥' + Number(i.unit_price).toLocaleString() },
        { label: 'age_tier', render: (i) => i.age_tier || '-' },
      ], 'カタログ未登録'));

      // 課金登録フォーム
      panel.appendChild(h('h2', null, '課金登録(台帳に1行追記)'));
      panel.appendChild(h('div', { class: 'row' },
        h('div', null,
          h('label', null, '世帯ID'),
          h('input', { id: 'ch-hid', placeholder: 'household_id' }),
        ),
        h('div', null,
          h('label', null, '品目'),
          h('select', { id: 'ch-item' },
            catalog.map(i => h('option', { value: i.item_id }, `${i.name} (¥${Number(i.unit_price).toLocaleString()})`)),
          ),
        ),
      ));
      panel.appendChild(h('div', { class: 'row' },
        h('div', null,
          h('label', null, 'billing_unit (例: MONTH#2026-05)'),
          h('input', { id: 'ch-bu' }),
        ),
        h('div', null,
          h('label', null, '数量'),
          h('input', { id: 'ch-qty', type: 'number', value: '1' }),
        ),
      ));
      panel.appendChild(h('label', null, '説明'));
      panel.appendChild(h('input', { id: 'ch-desc' }));
      panel.appendChild(h('div', { style: 'margin-top:1rem' },
        h('button', { class: 'primary', onclick: async () => {
          try {
            const r = await api('POST', '/charges', {
              household_id: $('#ch-hid').value,
              item_id: $('#ch-item').value,
              billing_unit: $('#ch-bu').value,
              quantity: Number($('#ch-qty').value),
              description: $('#ch-desc').value,
            });
            $('#ch-result').innerHTML = `登録: ${r.item_name} qty=${r.quantity} amount=¥${Number(r.amount).toLocaleString()}`;
          } catch (e) { $('#ch-result').innerHTML = `<span class="error">${e.message}</span>`; }
        }}, '台帳に追記'),
      ));
      panel.appendChild(h('div', { id: 'ch-result', class: 'info', style: 'margin-top:0.5rem' }));

      // 月次請求生成
      panel.appendChild(h('h2', null, '月次請求生成(billing_unit → 請求書スナップショット)'));
      panel.appendChild(h('label', null, 'billing_unit'));
      panel.appendChild(h('input', { id: 'gen-bu', placeholder: 'MONTH#2026-05' }));
      panel.appendChild(h('div', { style: 'margin-top:1rem' },
        h('button', { class: 'primary', onclick: async () => {
          try {
            const r = await api('POST', '/billing/generate', { billing_unit: $('#gen-bu').value });
            $('#gen-result').innerHTML = `生成: ${r.generated_count}件 (合計 ¥${r.invoices.reduce((s,i)=>s+Number(i.total),0).toLocaleString()})`;
          } catch (e) { $('#gen-result').innerHTML = `<span class="error">${e.message}</span>`; }
        }}, '請求書を生成'),
      ));
      panel.appendChild(h('div', { id: 'gen-result', class: 'info', style: 'margin-top:0.5rem' }));
    } catch (e) {
      panel.appendChild(h('div', { class: 'error' }, e.message));
    }
  }

  /* --- スタッフ: レポート --- */
  async function renderReports(panel) {
    panel.appendChild(h('h2', null, 'レポート'));

    // 月次売上
    panel.appendChild(h('h3', null, '月次売上'));
    panel.appendChild(h('div', null,
      h('label', null, '対象月 (YYYY-MM)'),
      h('input', { id: 'rep-period', placeholder: '2026-05' }),
      h('label', null, h('input', { id: 'rep-other', type: 'checkbox' }), ' EVENT等も含める'),
      h('div', { style: 'margin-top:0.5rem' },
        h('button', { class: 'primary', onclick: async () => {
          const p = $('#rep-period').value || '';
          const other = $('#rep-other').checked ? '&include_other_units=true' : '';
          try {
            const r = await api('GET', `/reports/monthly-revenue?period=${encodeURIComponent(p)}${other}`);
            const wrap = $('#rep-revenue'); wrap.innerHTML = '';
            wrap.appendChild(h('table', null,
              h('tr', null, h('th', null, '請求書件数'), h('td', null, String(r.invoice_count))),
              h('tr', null, h('th', null, '請求総額'), h('td', null, `¥${Number(r.total_billed).toLocaleString()}`)),
              h('tr', null, h('th', null, '入金済'), h('td', null, `¥${Number(r.total_paid).toLocaleString()}`)),
              h('tr', null, h('th', null, '未収'), h('td', null, `¥${Number(r.total_unpaid).toLocaleString()}`)),
            ));
          } catch (e) { $('#rep-revenue').innerHTML = `<span class="error">${e.message}</span>`; }
        }}, '集計'),
      ),
      h('div', { id: 'rep-revenue', style: 'margin-top:0.5rem' }),
    ));

    // 未収一覧
    panel.appendChild(h('h3', null, '未収一覧'));
    try {
      const r = await api('GET', '/reports/unpaid');
      panel.appendChild(h('p', null,
        `未収請求書 ${r.invoice_count}件 / ${r.household_count}世帯 / 合計 ¥${Number(r.total_unpaid).toLocaleString()}`));
      panel.appendChild(tableOf(r.by_household, [
        { label: '世帯', render: (b) => b.household_id.slice(0,8)+'..' },
        { label: '件数', key: 'count' },
        { label: '合計', render: (b) => '¥' + Number(b.total).toLocaleString() },
        { label: '内訳', render: (b) => b.items.map(it => `${it.billing_unit}(${it.status} ¥${Number(it.total).toLocaleString()})`).join('<br>') },
      ], '未収はありません'));
    } catch (e) { panel.appendChild(h('div', { class: 'error' }, e.message)); }

    // 在籍状況
    panel.appendChild(h('h3', null, '在籍状況'));
    try {
      const r = await api('GET', '/reports/enrollment');
      panel.appendChild(h('p', null, `総メンバー数: ${r.total_members}`));
      panel.appendChild(h('p', null, `在籍児童(ACTIVE child): ${r.active_children.count}`));
      panel.appendChild(h('div', null,
        h('strong', null, 'ステータス別:'), ' ',
        Object.entries(r.by_status).map(([k,v]) => `${k}=${v}`).join(' / '),
      ));
      panel.appendChild(h('div', null,
        h('strong', null, '学年別(在籍児童):'), ' ',
        Object.entries(r.active_children.by_grade).map(([k,v]) => `${k}=${v}`).join(' / '),
      ));
    } catch (e) { panel.appendChild(h('div', { class: 'error' }, e.message)); }
  }

  /* --- セッション情報タブ(デバッグ用) --- */
  function renderClaims(panel) {
    panel.appendChild(h('h2', null, 'セッション情報(JWT claims)'));
    panel.appendChild(h('pre', { class: 'json' }, JSON.stringify(state.claims, null, 2)));
  }

  /* ============ ルーター ============ */

  function isStaff() { return state.claims && state.claims['custom:user_type'] === 'staff'; }

  function appView() {
    const tabs = [
      { id: 'household', label: '自世帯', staffOnly: false, fn: renderHousehold },
      { id: 'invoices', label: '請求書', staffOnly: false, fn: renderInvoices },
      { id: 'announcements', label: 'お知らせ', staffOnly: false, fn: renderAnnouncements },
      { id: 'meetings', label: '議事録', staffOnly: false, fn: renderMeetings },
      { id: 'documents', label: '規程文書', staffOnly: false, fn: renderDocuments },
      { id: 'resolutions', label: '総会議決', staffOnly: false, fn: renderResolutions },
      { id: 'household-master', label: '世帯マスタ', staffOnly: true, fn: renderHouseholdMaster },
      { id: 'announce-create', label: 'お知らせ作成', staffOnly: true, fn: renderAnnouncementsCreate },
      { id: 'attendance', label: '出席記録', staffOnly: true, fn: renderAttendance },
      { id: 'meeting-create', label: '議事録作成', staffOnly: true, fn: renderMeetingCreate },
      { id: 'docs-upload', label: '規程アップロード', staffOnly: true, fn: renderDocsUpload },
      { id: 'resolution-create', label: '議案作成', staffOnly: true, fn: renderResolutionCreate },
      { id: 'billing', label: '請求運用', staffOnly: true, fn: renderBilling },
      { id: 'reports', label: 'レポート', staffOnly: true, fn: renderReports },
      { id: 'session', label: 'セッション', staffOnly: false, fn: renderClaims },
    ];
    const userType = state.claims['custom:user_type'] || 'unknown';
    const orgId = state.claims['custom:org_id'] || '';
    const email = state.claims.email || '';

    const header = h('header', null,
      h('h1', null, '学童SaaS 管理コンソール (STG)'),
      h('div', { class: 'user-info' },
        `${email} | ${userType} @ ${orgId} `,
        h('button', { class: 'ghost', style: 'margin-left:0.5rem', onclick: signOut }, 'ログアウト'),
      ),
    );
    const nav = h('nav', { class: 'tabs' },
      tabs.filter(t => !t.staffOnly || isStaff()).map(t =>
        h('button', {
          class: state.activeTab === t.id ? 'active' : '',
          onclick: () => { state.activeTab = t.id; render(); },
        }, t.label),
      ),
    );
    const panel = h('section', { class: 'panel' });
    const main = h('main', null, nav, panel);

    const currentTab = tabs.find(t => t.id === state.activeTab) || tabs[0];
    Promise.resolve(currentTab.fn(panel)).catch(e => {
      panel.appendChild(h('div', { class: 'error' }, String(e)));
    });

    const root = h('div', null, header, main);
    return root;
  }

  /* ============ Render ============ */

  function render() {
    const root = $('#app');
    root.innerHTML = '';
    root.appendChild(state.session ? appView() : loginView());
  }

  // 起動時に既存セッションを復元
  currentSession().then((r) => {
    if (r) { state.session = r.session; state.claims = parseClaims(r.session); }
    render();
  });
})();
