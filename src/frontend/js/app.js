/**
 * Novel Agent V7 — Writing Pipeline
 */
const App = {
    currentProjectId: null,
    ws: null,
    _assistantContext: null,
    _projects: [],
    _workflowDone: false,
    _scanAwaitingConfirmation: false,
    _pipelineState: {},  // step -> 'pending' | 'active' | 'running' | 'done'

    async init() {
        this._setupNav();
        this._setupFormHandlers();
        this._setupGlobalClicks();
        this._updateApiStatus();
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey && document.activeElement?.id === 'chat-input') {
                e.preventDefault(); this.sendAssistantMessage();
            }
        });
        await this._refreshProjects();
        this._navigate('workspace');
    },

    _setupGlobalClicks() {
        // Event delegation for project cards
        const cardsEl = document.getElementById('my-works-cards');
        if (cardsEl) {
            cardsEl.addEventListener('click', (e) => {
                const card = e.target.closest('[data-project-id]');
                if (card) this.openProject(card.dataset.projectId);
            });
        }
    },

    // ================================================================
    // Navigation
    // ================================================================
    _setupNav() {
        window.addEventListener('hashchange', () => this._route());
        ['nav-workspace','nav-my-works','nav-assistant'].forEach(id => {
            document.getElementById(id).addEventListener('click', (e) => {
                e.preventDefault();
                const v = id.replace('nav-','');
                if (v === 'my-works') { this.currentProjectId = null; if (this.ws) { this.ws.close(); this.ws = null; } }
                this._navigate(v);
            });
        });
    },

    _navigate(viewName) {
        document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
        document.querySelectorAll('#nav .nav-item').forEach(n => n.classList.remove('active'));
        const el = document.getElementById(`view-${viewName}`);
        if (el) el.classList.add('active');
        const navId = viewName === 'project' ? 'nav-my-works' : `nav-${viewName}`;
        const nav = document.getElementById(navId);
        if (nav) nav.classList.add('active');
        // Use replaceState to avoid triggering hashchange again
        if (window.location.hash !== `#${viewName}`) {
            history.replaceState(null, '', `#${viewName}`);
        }
        if (viewName === 'my-works') this._renderProjectList();
        if (viewName === 'project' && this.currentProjectId) this._loadProjectDetail();
        // Show/hide workspace header based on active project
        if (viewName === 'workspace') {
            if (this.currentProjectId) {
                // Project is loaded — keep header as is (set by openProject or startScan)
            } else {
                // No project — show default title, hide project header
                document.getElementById('workspace-default-title').style.display = '';
                document.getElementById('workspace-project-header').style.display = 'none';
            }
        }
    },

    _route() {
        const v = (window.location.hash || '#workspace').replace('#','');
        if (v === 'project') {
            if (this.currentProjectId) { this._navigate('project'); }
            else { this._navigate('my-works'); }
        } else {
            this._navigate(v);
        }
    },

    // ================================================================
    // My Library project list
    // ================================================================
    async _refreshProjects() {
        try { this._projects = await API.listProjects() || []; }
        catch (err) { console.error(err); }
    },

    _renderProjectList() {
        const container = document.getElementById('my-works-cards');
        if (!container) return;
        if (!this._projects.length) {
            container.innerHTML = '<p class="empty-state">No projects yet. Open the <a href="#workspace">Workspace</a> to get started.</p>';
            return;
        }
        container.innerHTML = this._projects.map(p => {
            const badge = p.current_chapter && p.total_chapters ? `${p.current_chapter}/${p.total_chapters}` : '';
            return `<div class="card" data-project-id="${p.project_id}" style="cursor:pointer">
                <h3>${this._esc(p.title || 'Untitled')}</h3>
                <div class="meta">${badge || 'Not started'}</div>
                <span class="status status-${p.status||'initialized'}">${p.status||'initialized'}</span>
            </div>`;
        }).join('');
    },

    async openProject(id) {
        this.currentProjectId = id;
        this._workflowDone = false;
        this._connectWS(id);
        this._initPipeline();
        try {
            const p = await API.getProject(id);
            const title = p.config?.title || 'Untitled';
            this._showProjectHeader(title);
            const meta = p.meta;
            if (meta && meta.current_phase && meta.current_phase !== 'idle') {
                this._restorePipelineState(meta);
            }
            if (p.awaiting_confirmation) {
                this._renderPhaseResult(p.awaiting_confirmation.step, p.awaiting_confirmation.data);
                this._showPhaseConfirmation(p.awaiting_confirmation.phase);
                const controls = document.getElementById(`${p.awaiting_confirmation.step}-confirm-area`);
                if (controls) controls.style.display = 'flex';
            }
        } catch(e) { /* ignore */ }
        this._navigate('workspace');
    },

    async _loadProjectDetail() {
        if (!this.currentProjectId) return;
        try {
            const p = await API.getProject(this.currentProjectId);
            document.getElementById('project-title').textContent = p.config.title || 'Untitled';
            document.getElementById('overview-content').innerHTML = Components.overviewEditable(p);
            // Detect if already complete
            const tc = p.meta?.total_chapters || 0;
            const cc = p.meta?.current_chapter || 0;
            if (tc > 0 && cc >= tc) this._workflowDone = true;
            this._setupTabs();
        } catch (err) { console.error(err); }
    },

    // ================================================================
    // Tabs
    // ================================================================
    _setupTabs() {
        document.querySelectorAll('#view-project .tab').forEach(tab => {
            tab.onclick = async () => {
                document.querySelectorAll('#view-project .tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('#view-project .tab-content').forEach(c => c.classList.remove('active'));
                tab.classList.add('active');
                document.getElementById(`tab-${tab.dataset.tab}`)?.classList.add('active');
                await this._loadTabContent(tab.dataset.tab);
            };
        });
    },

    async _loadTabContent(tab) {
        if (!this.currentProjectId) return;
        try {
            if (tab === 'topics') { document.getElementById('topics-content').innerHTML = Components.topicResearchView(); }
            else if (tab === 'bible') { const d = await API.getBible(this.currentProjectId); document.getElementById('bible-content').innerHTML = Components.bibleEditable(d); }
            else if (tab === 'characters') { const d = await API.getCharacters(this.currentProjectId); document.getElementById('characters-content').innerHTML = Components.charactersEditable(d); }
            else if (tab === 'outline') { const d = await API.getOutline(this.currentProjectId); document.getElementById('outline-content').innerHTML = Components.outlineEditable(d); }
            else if (tab === 'chapters') { const d = await API.getChapters(this.currentProjectId); let tc = 0; try { const p = await API.getProject(this.currentProjectId); tc = p.meta?.total_chapters || 0; } catch(e){} const allDone = this._workflowDone || (Array.isArray(d) && d.length > 0 && d.every(c => c.status === 'done')); document.getElementById('chapters-content').innerHTML = Components.chaptersView(d, {workflowDone: allDone, totalChapters: tc}); }
        } catch (err) { if (!err.message?.includes('404')) console.error(err); }
    },

    async viewChapter(num) {
        try {
            const ch = await API.getChapter(this.currentProjectId, num);
            let html = `<h3>Chapter ${num} ${Components._esc(ch.plan?.title||ch.title||'')}</h3>`;
            // Show status
            const statusLabels = { planned:'Planned', writing:'Writing', reviewing:'Reviewing', polishing:'Polishing', done:'Complete' };
            if (ch.status) html += `<p>Status: ${statusLabels[ch.status]||ch.status}</p>`;
            // Show review if available
            if (ch.review) html += Components.reviewScores(ch.review.dimension_scores);
            if (ch.review?.issues) html += Components.issuesList(ch.review.issues);
            html += '<hr style="margin:16px 0;border-color:var(--border)">';
            // Show content or explain what's missing
            if (ch.content) {
                let cleanContent = ch.content.replace(/^#{1,4}\s+.+$/gm, '');
                cleanContent = cleanContent.replace(/\n{3,}/g, '\n\n').trim();
                html += `<div style="display:flex;align-items:center;gap:8px;margin-top:12px"><strong>Chapter Text</strong><button class="btn btn-secondary btn-sm" onclick="App.toggleChapterEdit(${num})">Edit</button></div>`;
                html += `<div id="chapter-display-${num}" style="white-space:pre-wrap;line-height:2;font-size:1rem;margin-top:8px">${Components._esc(cleanContent)}</div>`;
                html += `<div id="chapter-editor-${num}" style="display:none"><textarea id="chapter-textarea-${num}" style="width:100%;min-height:300px;padding:12px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text-primary);font-family:inherit;font-size:0.95rem;line-height:1.8;resize:vertical">${Components._esc(cleanContent)}</textarea><button class="btn btn-success btn-sm" onclick="App.saveChapterEdit(${num})" style="margin-top:8px">Save</button></div>`;
            } else if (ch.plan) {
                html += `<p style="color:var(--text-secondary)">This chapter has an outline and is ready to draft.</p>`;
                if (ch.plan.goal) html += `<p><strong>Chapter Goal:</strong>${Components._esc(ch.plan.goal)}</p>`;
                if (ch.plan.scenes?.length) {
                    const sceneTexts = ch.plan.scenes.map(s => {
                        if (typeof s === 'string') {
                            // Strip scene labels and point-of-view markers.
                            let t = s.replace(/【[^】]+】/g, '').replace(/（POV.*?）|\(POV.*?\)/g, '').replace(/→/g, '').trim();
                            return Components._esc(t.substring(0, 80));
                        }
                        return Components._esc((s.setting || s.goal || '').substring(0, 80));
                    }).filter(Boolean);
                    if (sceneTexts.length) html += `<p><strong>Scene:</strong>${sceneTexts.join(' → ')}</p>`;
                }
                html += `<button class="btn btn-primary btn-sm" onclick="App.startWorkflow()" style="margin-top:8px">Continue Writing</button>`;
            } else {
                html += '<p style="color:var(--text-secondary)">Click Continue Writing to draft this chapter.</p>';
            }
            if (ch.content) {
                html += `<div style="margin-top:16px"><a href="${API.getChapterMdUrl(this.currentProjectId, num)}" class="btn btn-secondary btn-sm">Download Markdown</a></div>`;
            }
            document.getElementById('chapter-modal-body').innerHTML = html;
            document.getElementById('chapter-modal').classList.add('active');
            document.querySelector('.modal-close').onclick = () => document.getElementById('chapter-modal').classList.remove('active');
            document.getElementById('chapter-modal').onclick = (e) => { if (e.target === document.getElementById('chapter-modal')) document.getElementById('chapter-modal').classList.remove('active'); };
        } catch (err) { alert(`Loading failed: ${err.message}`); }
    },

    exportDocx() { if (this.currentProjectId) window.open(API.getExportDocxUrl(this.currentProjectId)); },
    exportMarkdown() { if (this.currentProjectId) window.open(API.getExportMdUrl(this.currentProjectId)); },

    // ================================================================
    // Inline Edit — generic toggle for any section
    // ================================================================
    toggleEdit(sectionId) {
        const display = document.getElementById(`${sectionId}-display`);
        const editor = document.getElementById(`${sectionId}-editor`);
        const btn = document.getElementById(`${sectionId}-edit-btn`);
        if (!display || !editor) return;
        const editing = editor.style.display !== 'none';
        if (editing) {
            const textarea = editor.querySelector('textarea');
            if (textarea) {
                const newValue = textarea.value;
                // Keep same font: update display with pre-wrap to match textarea
                display.innerHTML = `<div style="white-space:pre-wrap;font-family:inherit;font-size:0.95rem;line-height:1.7">${Components._esc(newValue)}</div>`;
                // Save to backend
                this._saveEdit(sectionId, newValue);
            }
            editor.style.display = 'none'; display.style.display = '';
            btn.textContent = 'Edit';
        } else {
            const textarea = editor.querySelector('textarea');
            if (textarea) textarea.value = display.innerText;
            editor.style.display = ''; display.style.display = 'none';
            btn.textContent = 'Save';
        }
    },

    async _saveEdit(sectionId, value) {
        if (!this.currentProjectId) return;
        try {
            // Determine artifact type from section ID prefix
            if (sectionId.startsWith('bible-')) {
                await API.updateBibleSection(this.currentProjectId, sectionId, value);
            } else if (sectionId.startsWith('char-')) {
                await API.updateCharacterSection(this.currentProjectId, sectionId, value);
            } else if (sectionId.startsWith('outline-')) {
                await API.updateOutlineSection(this.currentProjectId, sectionId, value);
            }
            document.getElementById('phase-label').textContent = 'Saved ✓';
            setTimeout(() => {
                const pl = document.getElementById('phase-label');
                if (pl && pl.textContent === 'Saved ✓') pl.textContent = 'Ready';
            }, 2000);
        } catch (err) {
            alert(`Save failed: ${err.message}`);
        }
    },

    // ================================================================
    // Workflow
    // ================================================================
    async startWorkflow() {
        if (!this.currentProjectId) return;
        try {
            await API.startWorkflow(this.currentProjectId);
            document.getElementById('phase-label').textContent = 'Starting...';
            document.getElementById('progress-fill').style.width = '2%';
        } catch (err) { alert(`Could not start: ${err.message}`); }
    },

    async confirmPhase() {
        if (!this.currentProjectId) return;
        const insp = document.getElementById('inspiration-input')?.value || '';
        try {
            await API.confirmPhase(this.currentProjectId, insp || null);
            document.querySelector('.phase-confirm')?.remove();
            document.getElementById('phase-label').textContent = 'Running...';
            document.getElementById('progress-fill').style.width = '5%';
        } catch (err) { alert(`Confirmation failed: ${err.message}`); }
    },

    async submitScan() {
        const projectId = this.currentProjectId;
        if (!projectId) return;
        const csv = document.getElementById('scan-csv').value.trim();
        const status = document.getElementById('scan-status');
        if (!csv) {
            status.textContent = 'Paste a CSV with at least one story observation.';
            return;
        }
        const submit = document.getElementById('btn-submit-scan');
        submit.disabled = true;
        try {
            await API.submitScan(projectId, csv);
            if (projectId !== this.currentProjectId) return;
            if (this._scanAwaitingConfirmation) {
                await API.retryPhase(projectId, 'platform_scan', null, true);
                return;
            }
            status.textContent = 'Snapshot saved. Starting analysis…';
            const run = await API.startWorkflow(projectId);
            if (projectId === this.currentProjectId && run.status !== 'started') {
                status.textContent = 'Snapshot saved for the next research run. The current run keeps its original evidence.';
            }
        } catch (err) {
            if (projectId === this.currentProjectId) status.textContent = err.message;
        } finally {
            submit.disabled = false;
        }
    },

    async confirmResearch() {
        const status = document.getElementById('scan-status');
        try {
            await API.confirmPhase(this.currentProjectId, null);
            this._scanAwaitingConfirmation = false;
            document.getElementById('scan-confirm-area').style.display = 'none';
            this._updatePipelineBadge('topic', 'active');
        } catch (err) {
            status.textContent = err.message;
        }
    },

    fillResearchExample() {
        document.getElementById('scan-csv').value = [
            'platform,list_name,source_url,captured_on,story_url,title,language,rank,tags,note',
            'wattpad,Fantasy example,https://www.wattpad.com/,2026-01-01,https://www.wattpad.com/story/101-example,Example Moon Garden,en,3,Fantasy|Romance,A gardener inherits a moonlit estate.',
            'royal_road,Rising Stars example,https://www.royalroad.com/fictions/rising-stars,2026-01-01,https://www.royalroad.com/fiction/201/example,Example Clockwork Map,en,,Fantasy|Progression,A map grows as its maker completes challenges.',
        ].join('\n');
    },

    /** Initialize the writing pipeline for the current project. */
    _initPipeline() {
        this._scanAwaitingConfirmation = false;
        const steps = ['scan','topic','arc','bible','chars','outline','write'];
        steps.forEach(s => { this._pipelineState[s] = 'pending'; });
        this._updatePipelineBadge('scan', 'active');
        // Show start button, hide everything else
        const btnStart = document.getElementById('btn-start-scan');
        if (btnStart) btnStart.style.display = '';
        const scanInput = document.getElementById('scan-input-area');
        if (scanInput) scanInput.style.display = 'none';
        document.getElementById('scan-csv').value = '';
        document.getElementById('scan-status').textContent = '';
        document.getElementById('topic-evidence-area').replaceChildren();
        ['scan-result-area','scan-confirm-area','topic-candidates-area','topic-synopsis-cards','topic-ai-area',
         'topic-confirm-area','arc-result-area','arc-confirm-area',
         'bible-result-area','bible-confirm-area','chars-result-area','chars-confirm-area',
         'outline-result-area','outline-confirm-area','write-result-area'].forEach(id => {
            const el = document.getElementById(id); if (el) el.style.display = 'none';
        });
    },

    /** Update a pipeline step badge */
    _updatePipelineBadge(step, status) {
        this._pipelineState[step] = status;
        const stepEl = document.getElementById(`pipeline-step-${step}`);
        const badgeEl = document.getElementById(`badge-${step}`);
        if (stepEl) {
            stepEl.classList.remove('active','done','running');
            if (status === 'active' || status === 'running') stepEl.classList.add(status);
            else if (status === 'done') stepEl.classList.add('done');
        }
        if (badgeEl) {
            const labels = { scan:'Research Snapshots', topic:'Topic Research', arc:'Opening Arc Outline', bible:'Worldbuilding', chars:'Character Creation', outline:'Outline Generation', write:'Chapter Writing' };
            const statusLabels = { pending:'Pending', active:'Current step', running:'Running...', done:'Complete ✓' };
            badgeEl.textContent = statusLabels[status] || status;
            badgeEl.className = 'pipeline-badge ' + (status === 'done' ? 'done' : status === 'running' ? 'running' : status === 'active' ? 'active' : '');
        }
    },

    /** Restore pipeline state from project metadata */
    _restorePipelineState(meta) {
        const phase = meta.current_phase || 'idle';
        const phaseOrder = { idle:0, platform_scan:1, topic_selection:2, mini_arc_outline:3, bible_construction:4, character_creation:5, master_outline:6 };
        const stepMap = { 0:'scan', 1:'topic', 2:'arc', 3:'bible', 4:'chars', 5:'outline' };
        const idx = phaseOrder[phase] || 0;
        Object.keys(stepMap).forEach(k => {
            const s = stepMap[k];
            if (parseInt(k) < idx) this._updatePipelineBadge(s, 'done');
            else if (parseInt(k) === idx) this._updatePipelineBadge(s, 'active');
        });
        // If chapters have been written, activate write step
        if (meta.current_chapter > 0) this._updatePipelineBadge('write', 'active');
        // Show the start button if we're at scan step
        if (idx <= 1) {
            const btnStart = document.getElementById('btn-start-scan');
            if (btnStart) btnStart.style.display = '';
        }
        // Hide scan input unless we have scan data
        const scanInput = document.getElementById('scan-input-area');
        if (scanInput) scanInput.style.display = 'none';
    },

    /** Skip scan and go directly to bible construction */
    async skipScan() {
        if (!this.currentProjectId) return;
        try {
            const run = await API.startWorkflow(this.currentProjectId, true);
            if (run.status !== 'started') return;
            this._updatePipelineBadge('scan', 'done');
            this._updatePipelineBadge('topic', 'done');
            this._updatePipelineBadge('arc', 'done');
            this._updatePipelineBadge('bible', 'active');
            document.getElementById('btn-start-scan').style.display = 'none';
            document.getElementById('scan-input-area').style.display = 'none';
        } catch (err) {
            document.getElementById('scan-status').textContent = err.message;
        }
    },

    async confirmDecision(decision) {
        if (!this.currentProjectId) return;
        const fb = document.getElementById('feedback-input')?.value || '';
        try { await API.submitDecision(this.currentProjectId, decision, fb || null, null); document.querySelector('.confirm-panel')?.remove(); }
        catch (err) { alert(`Submission failed: ${err.message}`); }
    },

    toggleChapterEdit(num) {
        const display = document.getElementById(`chapter-display-${num}`);
        const editor = document.getElementById(`chapter-editor-${num}`);
        if (!display || !editor) return;
        const editing = editor.style.display !== 'none';
        if (editing) {
            editor.style.display = 'none'; display.style.display = '';
        } else {
            document.getElementById(`chapter-textarea-${num}`).value = display.innerText;
            editor.style.display = ''; display.style.display = 'none';
        }
    },

    async saveChapterEdit(num) {
        const textarea = document.getElementById(`chapter-textarea-${num}`);
        if (!textarea) return;
        const newContent = textarea.value;
        try {
            await API.updateBibleSection(this.currentProjectId, `chapter-${num}`, newContent);
            document.getElementById(`chapter-display-${num}`).innerHTML = Components._esc(newContent);
            document.getElementById(`chapter-editor-${num}`).style.display = 'none';
            document.getElementById(`chapter-display-${num}`).style.display = '';
            document.getElementById('phase-label').textContent = 'Saved ✓';
            setTimeout(() => { const pl = document.getElementById('phase-label'); if (pl && pl.textContent === 'Saved ✓') pl.textContent = 'Ready'; }, 2000);
        } catch (err) { alert(`Save failed: ${err.message}`); }
    },

    async deleteChapter(num) {
        if (!this.currentProjectId || !confirm(`Delete Chapter ${num}? This action is permanent.`)) return;
        try {
            await API.deleteChapter(this.currentProjectId, num);
            this._loadTabContent('chapters');
        } catch (err) { alert(`Delete failed: ${err.message}`); }
    },

    async deleteCurrentProject() {
        if (!this.currentProjectId || !confirm('Delete this project?')) return;
        try {
            await API.deleteProject(this.currentProjectId);
            this.currentProjectId = null; this._workflowDone = false; if (this.ws) { this.ws.close(); this.ws = null; }
            await this._refreshProjects();
            this._navigate('my-works');
        } catch (err) { alert(`Delete failed: ${err.message}`); }
    },

    // ================================================================
    // WebSocket
    // ================================================================
    _connectWS(projectId) {
        if (this.ws) this.ws.close();
        const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
        this.ws = new WebSocket(`${proto}//${location.host}/ws/${projectId}`);
        this.ws.onopen = () => this._updateApiStatus(true);
        this.ws.onmessage = (event) => {
            if (this.currentProjectId === projectId && this.ws === event.target) {
                this._handleWSMessage(JSON.parse(event.data));
            }
        };
        this.ws.onclose = () => this._updateApiStatus(false);
        this.ws.onerror = () => this._updateApiStatus(false);
    },

    _handleWSMessage(msg) {
        const { type, phase, progress, message, chapter, scores, token, data: msgData } = msg;
        const pb = document.getElementById('progress-fill');
        const pl = document.getElementById('phase-label');
        const pm = { platform_scan:'Research Snapshots', topic_selection:'Topic Research', mini_arc_outline:'Opening Arc Outline', bible_construction:'Building the World', character_creation:'Creating Characters', master_outline:'Generating Outline', chapter_planning:'Planning Chapters', chapter_writing:'Writing', quality_review:'Reviewing', polish_revision:'Polishing', memory_update:'Updating Memory' };
        const tm = { platform_scan:'topics', topic_selection:'topics', mini_arc_outline:'topics', bible_construction:'bible', character_creation:'characters', master_outline:'outline', chapter_planning:'chapters', chapter_writing:'chapters' };
        // Pipeline badge mapping
        const phaseToStep = { platform_scan:'scan', topic_selection:'topic', mini_arc_outline:'arc', bible_construction:'bible', character_creation:'chars', master_outline:'outline' };

        switch (type) {
            case 'phase_update':
                if (pl) pl.textContent = `${pm[phase]||phase} · ${message||''}`;
                if (pb) pb.style.width = `${(progress||0)*100}%`;
                if (tm[phase]) this._switchTab(tm[phase]);
                // Update pipeline badge to running
                if (phaseToStep[phase]) this._updatePipelineBadge(phaseToStep[phase], 'running');
                // Hide scan start button when scan starts
                if (phase === 'platform_scan') {
                    const btnStart = document.getElementById('btn-start-scan');
                    if (btnStart) btnStart.style.display = 'none';
                }
                break;
            case 'phase_complete':
                if (pl) pl.textContent = `${pm[phase]||phase} complete ✓`;
                if (pb) pb.style.width = '100%';
                if (phaseToStep[phase]) {
                    const step = phaseToStep[phase];
                    this._updatePipelineBadge(step, 'done');
                    if (msgData) this._renderPhaseResult(step, msgData);
                    // Show confirm UI per step
                    if (step === 'topic') {
                        document.getElementById('topic-confirm-area').style.display = 'flex';
                    } else if (step === 'arc') {
                        document.getElementById('arc-confirm-area').style.display = 'flex';
                    } else if (step === 'bible') {
                        document.getElementById('bible-confirm-area').style.display = 'flex';
                    } else if (step === 'chars') {
                        document.getElementById('chars-confirm-area').style.display = 'flex';
                    } else if (step === 'outline') {
                        document.getElementById('outline-confirm-area').style.display = 'flex';
                    }
                }
                if (tm[phase]) { this._switchTab(tm[phase]); this._loadTabContent(tm[phase]); }
                break;
            case 'phase_blocked': this._showPhaseConfirmation(phase); break;
            case 'token': if (token) this._appendStreamToken(token); else this._onStreamEnd(); break;
            case 'stream_end': this._onStreamEnd(); break;
            case 'chapter_complete':
                this._updatePipelineBadge('write', 'active');
                if (chapter && scores) {
                    const ov = document.getElementById('overview-content');
                    if (ov && !ov.querySelector('.confirm-panel')) ov.insertAdjacentHTML('beforeend', Components.confirmPanel(chapter, { overall_score:scores.overall_score||7, dimension_scores:scores, issues:[] }));
                }
                break;
            case 'workflow_complete':
                this._workflowDone = true;
                this._updatePipelineBadge('write', 'done');
                if (pl) pl.textContent = 'All steps complete ✓';
                if (pb) pb.style.width = '100%';
                if (this.currentProjectId) this._loadTabContent('chapters');
                this._refreshProjects();
                break;
            case 'error':
                if (phase === 'platform_scan' || this._pipelineState.scan === 'running') {
                    document.getElementById('scan-status').textContent = message || 'Research failed. Retry the import.';
                    document.getElementById('scan-input-area').style.display = 'block';
                } else {
                    alert(message || 'Workflow failed.');
                }
                break;
        }
    },

    _renderPhaseResult(step, data) {
        if (!data) return;
        try {
            if (step === 'scan') this._renderScanResult(data);
            else if (step === 'topic') this._renderTopicResult(data);
            else if (step === 'arc') this._renderArcResult(data);
            else if (step === 'bible') this._renderBibleResult(data);
            else if (step === 'chars') this._renderCharsResult(data);
            else if (step === 'outline') this._renderOutlineResult(data);
            else if (step === 'write') this._renderWriteResult(data);
        } catch(e) { console.error('Render phase result error:', e); }
    },

    _renderScanResult(data) {
        const el = document.getElementById('scan-result-area');
        const coverage = data.coverage || {};
        const snapshots = data.snapshots || [];
        const names = { wattpad: 'Wattpad', royal_road: 'Royal Road' };
        const esc = Components._esc;
        const cards = Object.entries(names).map(([platform, name]) => {
            const lists = snapshots.filter(snapshot => snapshot.platform === platform);
            const genres = new Map();
            for (const list of lists) {
                for (const story of list.observations) {
                    for (const tag of story.tags) {
                        const label = tag.trim().toLowerCase();
                        if (!genres.has(label)) genres.set(label, {tag, refs: new Set()});
                        genres.get(label).refs.add(story.story_ref);
                    }
                }
            }
            const tags = Array.from(genres.values()).sort((a, b) => b.refs.size - a.refs.size)
                .slice(0, 8).map(({tag, refs}) => `${esc(tag)} (${refs.size})`).join(', ');
            const listCards = lists.map(list => `
                <h5><a href="${esc(list.source_url)}" target="_blank" rel="noopener noreferrer">${esc(list.list_name)}</a>
                    · ${esc(list.captured_on)} · ${list.observations.length} observations</h5>
                ${list.filters ? `<p>${esc(list.filters)}</p>` : ''}
                <ul>${list.observations.map(story => `<li>
                    ${story.rank ? `#${story.rank} · ` : ''}
                    <a href="${esc(story.story_url)}" target="_blank" rel="noopener noreferrer">${esc(story.title)}</a>
                    <small>${esc(story.story_ref)}${story.language === 'unknown' ? ' · language unknown' : ''}</small>
                </li>`).join('')}</ul>
            `).join('');
            return `<section class="scan-mini-card"><h4>${name}</h4>
                <p>${coverage[platform] ? `${coverage[platform]} unique sampled stories` : 'No imported observations'}</p>
                ${tags ? `<p>Sampled genres and tags · ${tags}</p>` : ''}${listCards}</section>`;
        }).join('');
        const label = coverage.wattpad && coverage.royal_road ? 'Both sources sampled'
            : snapshots.length ? 'Partial coverage · one source sampled' : 'No current research snapshot';
        el.innerHTML = `<p><strong>${label}</strong></p>${data.historical ? '<p>This project has historical research from earlier sources.</p>' : ''}${cards}`;
        el.style.display = 'block';
        document.getElementById('scan-status').textContent = '';
        document.getElementById('scan-input-area').style.display = 'none';
        document.getElementById('btn-start-scan').style.display = snapshots.length ? 'none' : '';
    },

    _renderTopicResult(data) {
        this._topicScores = data.scores?.scores || [];
        this._topicTitleData = data.title_synopsis || [];
        this._topicCandidates = data.candidates?.topics || [];
        this._topicCrossPlatform = data.cross_platform;
        this._checkedCandidates = Object.create(null);
        this._synopsisCards = [];
        this._selectedSynopsisIdx = -1;

        const coverage = data.coverage || {};
        const evidenceArea = document.getElementById('topic-evidence-area');
        const overlap = Object.keys(data.shared_tags || {}).slice(0, 8).map(Components._esc).join(', ');
        const names = { wattpad: 'Wattpad', royal_road: 'Royal Road' };
        const findings = (data.cross_platform?.entries || []).flatMap(entry =>
            Object.entries(entry.findings || {}).map(([source, finding]) => {
                const refs = entry.evidence?.[source] || [];
                return `<li><strong>${Components._esc(entry.genre)} · ${names[source]}</strong>
                    ${Components._esc(finding)} <small>[${Components._esc(refs.join(', '))}]</small></li>`;
            })
        );
        evidenceArea.innerHTML = `
            <p>Sample coverage · Wattpad: ${coverage.wattpad || 0} · Royal Road: ${coverage.royal_road || 0}</p>
            ${overlap ? `<p>Tags observed in English-language samples on both platforms · ${overlap}</p>` : ''}
            ${findings.length ? `<ul>${findings.join('')}</ul>` : '<p>No validated findings from the current sources. Use these concepts for brainstorming.</p>'}
            ${data.historical ? '<p>This project has historical research from earlier sources.</p>' : ''}
        `;

        const allTopics = [];
        const seen = new Set();

        // Priority 1: Scored topics
        for (const t of this._topicScores) {
            const name = t.genre_name;
            if (name && !seen.has(name)) { seen.add(name); allTopics.push({name, score: t.total_score, data: t}); }
        }
        // Priority 2: Candidates without scores
        for (const t of this._topicCandidates) {
            const name = t.genre_name;
            if (name && !seen.has(name)) { seen.add(name); allTopics.push({name, score: 0, data: t}); }
        }

        const candidatesArea = document.getElementById('topic-candidates-area');
        const candidatesList = document.getElementById('topic-candidates-list');
        const aiArea = document.getElementById('topic-ai-area');

        if (!allTopics.length) {
            // No topics at all — show retry UI with helpful context
            if (candidatesArea) candidatesArea.style.display = 'none';
            if (aiArea) {
                aiArea.style.display = 'block';
                const scanOk = Object.values(coverage).some(count => count > 0);
                const msg = scanOk
                    ? '⚠️ The scan completed, but no concepts were generated. Retry or enter your own idea below.'
                    : '⚠️ No concepts were generated. Try importing more observations or enter your own idea below.';
                aiArea.querySelector('p').innerHTML = msg +
                    '&nbsp;<button class="btn btn-warning btn-sm" onclick="App.retryPhase(\'topic_selection\')" style="margin-left:8px">🔄 Regenerate Concepts</button>';
                aiArea.querySelector('p').style.color = 'var(--warning)';
            }
            return;
        }

        // Show candidates
        if (candidatesArea && candidatesList) {
            candidatesArea.style.display = 'block';
            let listHtml = '';
            allTopics.slice(0, 12).forEach((t, i) => {
                const name = Components._esc(t.name);
                const score = t.score ? (t.score).toFixed(1) : '—';
                const fits = Object.entries(names).map(([source, label]) => {
                    const fit = t.data.platform_fit?.[source];
                    return fit ? `${label} ${fit.score}/10 (${Components._esc(fit.evidence.join(', '))})`
                        : `${label} unknown`;
                }).join(' · ');
                listHtml += `<button type="button" class="topic-candidate-row" data-index="${i}">
                    <span class="topic-candidate-check">✓</span>
                    <span class="topic-candidate-name">${name}<small style="display:block">${fits}</small></span>
                    <span class="topic-candidate-score">${score}${t.score ? ' pts' : ''}</span>
                </button>`;
            });
            candidatesList.innerHTML = listHtml;
            candidatesList.querySelectorAll('[data-index]').forEach((row) => {
                row.addEventListener('click', () => this.toggleCandidate(allTopics[Number(row.dataset.index)].name, row));
            });
            this._allTopics = allTopics.slice(0, 12);
        }

        if (aiArea) aiArea.style.display = 'block';
    },

    /** Toggle candidate checkbox */
    toggleCandidate(genreName, row) {
        this._checkedCandidates[genreName] = !this._checkedCandidates[genreName];
        if (row) row.classList.toggle('checked', this._checkedCandidates[genreName]);
        const count = Object.values(this._checkedCandidates).filter(Boolean).length;
        const hint = document.getElementById('candidate-hint');
        if (hint) hint.textContent = `${count} selected`;
    },

    /** Generate synopsis cards for checked candidates, calling LLM on demand */
    async generateSynopses() {
        const checked = Object.entries(this._checkedCandidates).filter(([_,v]) => v).map(([k]) => k);
        if (!checked.length) { alert('Select at least one concept.'); return; }

        const cardsContainer = document.getElementById('topic-synopsis-cards');
        if (!cardsContainer) return;
        cardsContainer.style.display = 'block';
        cardsContainer.innerHTML = '<p style="font-size:0.82rem;color:var(--text-secondary);margin-bottom:8px">📝 Generating titles and synopses...</p>';

        this._synopsisCards = [];
        this._selectedSynopsisIdx = -1;

        const titleData = this._topicTitleData || [];
        const inspEl = document.getElementById('topic-ai-input');
        const inspiration = inspEl?.value?.trim() || '';

        for (let idx = 0; idx < checked.length; idx++) {
            const genreName = checked[idx];
            const ts = titleData.find(t => t.genre_name === genreName);
            let title = ts?.final_title || '';
            let synopsis = ts?.final_synopsis || '';

            // If no pre-generated synopsis, call API to generate on demand
            if (!title || !synopsis) {
                try {
                    cardsContainer.innerHTML = `<p style="font-size:0.82rem;color:var(--text-secondary);margin-bottom:8px">📝 Generating titles and synopses for ${Components._esc(genreName)}...</p>`;
                    const result = await API.generateSynopsis(this.currentProjectId, genreName, inspiration);
                    title = result.final_title || genreName;
                    synopsis = result.final_synopsis || '';
                } catch (err) {
                    console.error('Synopsis generation failed for', genreName, err);
                    title = title || genreName;
                    synopsis = synopsis || inspiration || '';
                }
            }

            const card = { genreName, title, synopsis, editedTitle: title, editedSynopsis: synopsis };
            this._synopsisCards.push(card);
            const cardIdx = this._synopsisCards.length - 1;
            const cardHtml = this._renderSynopsisCard(card, cardIdx);
            if (idx === 0) {
                cardsContainer.innerHTML = '<p style="font-weight:600;font-size:0.82rem;margin-bottom:6px">📝 Select a title and synopsis. You can edit both.</p>';
            }
            cardsContainer.insertAdjacentHTML('beforeend', cardHtml);
        }

        // Show confirm bar after all cards generated
        document.getElementById('topic-confirm-area').style.display = 'flex';
    },

    /** Render a single synopsis card */
    _renderSynopsisCard(card, idx) {
        const name = Components._esc(card.genreName);
        return `<div class="synopsis-card" id="synopsis-card-${idx}">
            <div class="synopsis-card-header">
                <div class="synopsis-radio" onclick="App.selectSynopsisCard(${idx})" title="Select this title"></div>
                <input class="synopsis-title-input" id="synopsis-title-${idx}" value="${Components._esc(card.editedTitle)}" onchange="App._synopsisCards[${idx}].editedTitle=this.value">
            </div>
            <div class="synopsis-body">
                <textarea class="synopsis-desc-input" id="synopsis-desc-${idx}" onchange="App._synopsisCards[${idx}].editedSynopsis=this.value">${Components._esc(card.editedSynopsis)}</textarea>
            </div>
            <div class="synopsis-meta">
                <span>Genre: ${name}</span>
            </div>
        </div>`;
    },

    /** Radio-select a synopsis card */
    selectSynopsisCard(idx) {
        this._selectedSynopsisIdx = idx;
        document.querySelectorAll('.synopsis-card').forEach((el, i) => {
            el.classList.toggle('selected', i === idx);
        });
    },

    /** AI generate titles based on user inspiration */
    async aiGenerateTitles() {
        const input = document.getElementById('topic-ai-input');
        const resultsEl = document.getElementById('topic-ai-results');
        const btn = document.getElementById('btn-ai-generate');
        const insp = input?.value?.trim();
        if (!insp) { alert('Enter an idea first.'); return; }

        btn.textContent = 'Generating...'; btn.disabled = true;
        resultsEl.innerHTML = '<span style="color:var(--text-secondary);font-size:0.82rem">Analyzing rankings and generating titles...</span>';

        try {
            const r = await fetch('/api/projects/' + this.currentProjectId + '/ai-titles', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({inspiration: insp})
            });
            if (!r.ok) throw new Error((await r.json()).detail || 'Request failed');
            const data = await r.json();
            if (data.titles?.length) {
                resultsEl.innerHTML = '<p style="font-size:0.78rem;color:var(--text-secondary);margin-bottom:4px">Click a generated title to add it to the candidates.</p>';
                data.titles.forEach(t => {
                    const chip = document.createElement('span');
                    chip.className = 'tag-chip purple';
                    chip.style.cssText = 'cursor:pointer;margin:3px;font-size:0.82rem;padding:4px 12px';
                    chip.textContent = t;
                    chip.onclick = () => {
                        input.value = t;
                        // Add to checked candidates
                        const name = t;
                        if (!this._checkedCandidates[name]) {
                            this._checkedCandidates[name] = true;
                            const index = this._allTopics.findIndex(item => item.name === name);
                            const row = index >= 0 ? document.querySelector(`.topic-candidate-row[data-index="${index}"]`) : null;
                            if (row) row.classList.add('checked');
                            else {
                                // Add a new row
                                this._allTopics.push({name, score: 0, data: {}});
                                const list = document.getElementById('topic-candidates-list');
                                const newRow = document.createElement('button');
                                newRow.type = 'button';
                                newRow.className = 'topic-candidate-row checked';
                                newRow.dataset.index = this._allTopics.length - 1;
                                newRow.innerHTML = `<div class="topic-candidate-check">✓</div><span class="topic-candidate-name">${Components._esc(name)}</span><span class="topic-candidate-score">AI</span>`;
                                newRow.onclick = () => App.toggleCandidate(name, newRow);
                                list.appendChild(newRow);
                            }
                            const count = Object.values(this._checkedCandidates).filter(Boolean).length;
                            const hint = document.getElementById('candidate-hint');
                            if (hint) hint.textContent = `${count} selected`;
                        }
                    };
                    resultsEl.appendChild(chip);
                });
            } else {
                resultsEl.innerHTML = '<span style="color:var(--text-secondary);font-size:0.82rem">No titles were generated. Try a more specific idea.</span>';
            }
        } catch (err) {
            resultsEl.innerHTML = `<span style="color:var(--error);font-size:0.82rem">Generation failed: ${err.message}</span>`;
        } finally {
            btn.textContent = 'Generate'; btn.disabled = false;
        }
    },

    _renderArcResult(data) {
        const el = document.getElementById('arc-result-area');
        if (!el) return;
        const outlines = data.mini_arc_outline || data;
        const keys = Object.keys(outlines).filter(k => k !== 'mini_arc_outline');
        // Filter entries that actually have chapter data (not just empty array)
        const entries = keys.map(k => [k, outlines[k]]).filter(([_,v]) => v?.chapters?.length > 0);
        let html = '';

        if (!entries.length) {
            el.innerHTML = `<div style="padding:16px;border:1px dashed var(--warning);border-radius:8px;text-align:center">
                <p style="color:var(--warning);margin-bottom:12px">⚠️ The model could not generate a complete outline.</p>
                <p style="font-size:0.82rem;color:var(--text-secondary);margin-bottom:12px">Add more detail below and regenerate the outline.</p>
                <button class="btn btn-warning" onclick="App.retryPhase('mini_arc_outline')" style="margin-right:8px">🔄 Regenerate Outline</button>
            </div>`;
            el.style.display = 'block';
            // Show the confirm/inspiration area so user can add details
            const confirmEl = document.getElementById('arc-confirm-area');
            if (confirmEl) confirmEl.style.display = 'flex';
            return;
        }

        // Stats
        const totalChapters = entries.reduce((sum, [_,v]) => sum + (v.chapters?.length||0), 0);
        html += '<div class="dash-grid">';
        html += `<div class="dash-tile accent"><div class="dash-num">${entries.length}</div><div class="dash-label">Outlines</div></div>`;
        html += `<div class="dash-tile success"><div class="dash-num">${totalChapters}</div><div class="dash-label">Total Chapters</div></div>`;
        html += `<div class="dash-tile warning"><div class="dash-num">20,000</div><div class="dash-label">Words per Outline</div></div>`;
        html += '</div>';

        entries.forEach(([genre, arc]) => {
            html += `<div style="margin-bottom:12px"><p style="font-weight:600;margin-bottom:6px">📋 ${Components._esc(genre)} · ${Components._esc(arc.total_words||'About 20,000 words')}</p>`;
            html += '<div class="timeline">';
            (arc.chapters||[]).slice(0, 10).forEach((c, i) => {
                html += `<div class="tl-node${i<3?' done':''}"><div class="tl-card"><div class="tl-title">Chapter ${c.chapter_number||(i+1)}</div><div class="tl-sub">${Components._esc((c.goal||c.conflict||'').substring(0,50))}</div></div></div>`;
            });
            html += '</div></div>';
        });

        el.innerHTML = html; el.style.display = 'block';
    },

    _renderBibleResult(data) {
        const el = document.getElementById('bible-result-area');
        if (!el) return;
        const w = data.world || {};
        const factions = data.factions || [];
        const themes = data.themes || [];
        const style = data.style_contract || {};
        let html = '';

        // Dashboard tiles
        html += '<div class="dash-grid">';
        html += `<div class="dash-tile accent"><div class="dash-num">${w.name ? 1 : 0}</div><div class="dash-label">Worldbuilding</div></div>`;
        html += `<div class="dash-tile success"><div class="dash-num">${factions.length}</div><div class="dash-label">Factions</div></div>`;
        html += `<div class="dash-tile warning"><div class="dash-num">${themes.length}</div><div class="dash-label">Core Themes</div></div>`;
        html += `<div class="dash-tile accent"><div class="dash-num">${w.magic_system?'✓':'—'}</div><div class="dash-label">Power System</div></div>`;
        html += '</div>';

        // World summary
        if (w.name) {
            html += `<div style="margin-bottom:8px"><strong>${Components._esc(w.name)}</strong> <span class="tag-chip blue">${Components._esc(w.world_type||'')}</span></div>`;
            if (w.geography) html += `<p style="font-size:0.8rem;color:var(--text-secondary);margin-bottom:4px">🌏 ${Components._esc(w.geography.substring(0,100))}</p>`;
            if (w.culture) html += `<p style="font-size:0.8rem;color:var(--text-secondary);margin-bottom:4px">🏛 ${Components._esc(w.culture.substring(0,100))}</p>`;
            if (w.technology_level) html += `<p style="font-size:0.8rem;color:var(--text-secondary);margin-bottom:4px">⚙ ${Components._esc(w.technology_level)}</p>`;
        }

        // Faction chips
        if (factions.length) {
            html += '<p style="font-weight:600;font-size:0.8rem;margin-top:8px">Factions:</p>';
            factions.forEach(f => {
                html += `<span class="tag-chip purple">${Components._esc(f.name)}</span>`;
            });
            html += '<br>';
        }

        // Style contract summary
        if (style.tone) {
            html += '<p style="font-size:0.78rem;color:var(--text-secondary);margin-top:8px">Style: ';
            html += `<span class="tag-chip gray">${Components._L(Components.TONE, style.tone)}</span>`;
            if (style.pacing_preference) html += `<span class="tag-chip gray">${Components._L(Components.PACING, style.pacing_preference)}</span>`;
            if (style.sentence_style) html += `<span class="tag-chip gray">${Components._L(Components.SENTENCE, style.sentence_style)}</span>`;
            html += '</p>';
        }

        el.innerHTML = html; el.style.display = 'block';
    },

    _renderCharsResult(data) {
        const el = document.getElementById('chars-result-area');
        if (!el) return;
        const chars = data.characters || {};
        const list = Object.values(chars);
        let html = '';

        // Stats
        html += '<div class="dash-grid">';
        html += `<div class="dash-tile accent"><div class="dash-num">${list.length}</div><div class="dash-label">Total Characters</div></div>`;
        const roles = { protagonist:0, antagonist:0, deuteragonist:0, supporting:0, mentor:0 };
        list.forEach(c => { if (roles[c.role] !== undefined) roles[c.role]++; });
        html += `<div class="dash-tile success"><div class="dash-num">${roles.protagonist||0}</div><div class="dash-label">Protagonist</div></div>`;
        html += `<div class="dash-tile warning"><div class="dash-num">${roles.antagonist||0}</div><div class="dash-label">Antagonist</div></div>`;
        html += '</div>';

        // Character cards
        list.forEach(c => {
            const roleLabel = Components._L(Components.ROLE, c.role) || '';
            const archetypeLabel = Components._L(Components.ARCHETYPE, c.archetype) || '';
            html += `<div class="char-card">
                <span class="char-name">${Components._esc(c.name)}</span>
                ${roleLabel?`<span class="tag-chip purple">${roleLabel}</span>`:''}
                ${archetypeLabel?`<span class="tag-chip blue">${archetypeLabel}</span>`:''}
                <p style="font-size:0.8rem;margin-top:4px;color:var(--text-secondary)">${Components._esc((c.personality||'').substring(0,80))}</p>
                ${c.motivation?`<p style="font-size:0.78rem;color:var(--text-secondary)">Motivation: ${Components._esc(c.motivation.substring(0,60))}</p>`:''}
            </div>`;
        });

        el.innerHTML = html; el.style.display = 'block';
    },

    _renderOutlineResult(data) {
        const el = document.getElementById('outline-result-area');
        if (!el) return;
        let html = '';
        const volumes = data.volumes || [];
        const mainPlot = data.main_plot || [];
        const subplots = data.subplots || [];
        const tps = data.major_turning_points || [];

        // Stats
        html += '<div class="dash-grid">';
        html += `<div class="dash-tile accent"><div class="dash-num">${volumes.length}</div><div class="dash-label">Volumes</div></div>`;
        html += `<div class="dash-tile success"><div class="dash-num">${data.chapter_count||'?'}</div><div class="dash-label">Planned Chapters</div></div>`;
        html += `<div class="dash-tile warning"><div class="dash-num">${mainPlot.length+subplots.length}</div><div class="dash-label">Storylines</div></div>`;
        html += '</div>';

        // Logline
        if (data.logline) {
            html += `<p style="font-size:0.85rem;color:var(--text-secondary);margin-bottom:10px;font-style:italic">"${Components._esc(data.logline.substring(0,120))}"</p>`;
        }

        // Volume tree
        if (volumes.length) {
            html += '<div class="volume-tree">';
            volumes.forEach(v => {
                html += `<div class="volume-node">
                    <div class="volume-header"><span class="vol-num">${v.number||'?'}</span>${Components._esc(v.title||'Untitled')}</div>
                    <div class="volume-body">Chapters ${v.start_chapter||'?'}-${v.end_chapter||'?'} · ${Components._esc(v.logline||'')}</div>
                </div>`;
            });
            html += '</div>';
        }

        // Turning points timeline
        if (tps.length) {
            html += '<p style="font-weight:600;font-size:0.8rem;margin-top:10px">⏳ Key Turning Points</p>';
            html += '<div class="timeline">';
            tps.forEach(tp => {
                html += `<div class="tl-node done"><div class="tl-card"><div class="tl-title">Chapter ${tp.chapter||'?'}: ${Components._L(Components.TURNING, tp.turning_type)}</div><div class="tl-sub">${Components._esc((tp.description||'').substring(0,80))}</div></div></div>`;
            });
            html += '</div>';
        }

        el.innerHTML = html; el.style.display = 'block';
    },

    _renderWriteResult(data) {
        const el = document.getElementById('write-result-area');
        if (!el) return;
        let html = '';
        // Fetch chapters via API for up-to-date data
        if (this.currentProjectId) {
            API.getChapters(this.currentProjectId).then(chapters => {
                const list = Array.isArray(chapters) ? chapters : [];
                const done = list.filter(c => c.status === 'done').length;
                html += '<div class="dash-grid">';
                html += `<div class="dash-tile accent"><div class="dash-num">${done}</div><div class="dash-label">Complete</div></div>`;
                html += `<div class="dash-tile success"><div class="dash-num">${list.length}</div><div class="dash-label">Total Chapters</div></div>`;
                html += '</div>';
                if (list.length) {
                    html += '<div class="chapter-progress-grid">';
                    list.forEach(c => {
                        const isDone = c.status === 'done';
                        html += `<div class="chapter-progress-chip ${isDone?'done':'active'}" title="Chapter ${c.chapter_number}">${c.chapter_number}</div>`;
                    });
                    html += '</div>';
                }
                el.innerHTML = html; el.style.display = 'block';
            }).catch(() => {
                el.innerHTML = '<p style="font-size:0.85rem;color:var(--text-secondary)">Drafting chapters...</p>';
                el.style.display = 'block';
            });
        }
    },

    _appendStreamToken(token) {
        let el = document.getElementById('stream-output');
        if (!el) {
            const at = document.querySelector('#view-project .tab-content.active');
            if (!at) return;
            const c = document.createElement('div'); c.className = 'stream-container';
            c.innerHTML = '<div class="stream-header">Generating...</div><pre id="stream-output" class="stream-text streaming"></pre>';
            at.insertBefore(c, at.firstChild); el = document.getElementById('stream-output');
        }
        if (el) { el.textContent += token; el.scrollTop = el.scrollHeight; }
    },

    _onStreamEnd() {
        document.getElementById('stream-output')?.classList.remove('streaming');
        setTimeout(() => { const at = document.querySelector('#view-project .tab.active'); if (at) this._loadTabContent(at.dataset.tab); }, 500);
    },

    _showPhaseConfirmation(phase) {
        if (phase === 'platform_scan') {
            this._scanAwaitingConfirmation = true;
            document.getElementById('scan-confirm-area').style.display = 'block';
        }
        document.querySelector('.phase-confirm')?.remove();
        const ac = document.querySelector('#view-project .tab-content.active');
        if (!ac) return;
        ac.insertAdjacentHTML('beforeend', Components.phaseConfirmPanel(phase));
    },

    _switchTab(n) { document.querySelector(`#view-project .tab[data-tab="${n}"]`)?.click(); },

    // ================================================================
    // Writing Assistant
    // ================================================================
    async handleAssistantFile(event) {
        const file = event.target.files[0]; if (!file) return;
        const fd = new FormData(); fd.append('file', file);
        try {
            const r = await fetch('/api/projects/default/editor/upload', { method:'POST', body:fd });
            if (!r.ok) throw new Error((await r.json()).detail);
            const d = await r.json(); this._assistantContext = d.file_id;
            document.getElementById('assistant-file-name').textContent = `Uploaded: ${d.filename}`;
            this._addChatMsg('assistant', `Uploaded ${d.filename} (${d.size.toLocaleString()} characters).\n\nPreview:\n${d.preview}`);
        } catch (err) { alert(`Upload failed: ${err.message}`); }
    },

    quickChat(msg) { document.getElementById('chat-input').value = msg; this.sendAssistantMessage(); },

    async sendAssistantMessage() {
        const input = document.getElementById('chat-input'); const msg = input.value.trim(); if (!msg) return;
        const mode = document.getElementById('chat-mode')?.value || 'chat'; input.value = '';
        this._addChatMsg('user', msg);
        const div = this._addChatMsg('assistant', ''); const td = div.querySelector('.chat-text');
        try {
            const r = await fetch('/api/projects/default/editor/chat', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ message:msg, mode, context:this._assistantContext||null }) });
            if (!r.ok) throw new Error((await r.json()).detail);
            const reader = r.body.getReader(); const dec = new TextDecoder(); let buf = '';
            while (true) {
                const { done, value } = await reader.read(); if (done) break;
                buf += dec.decode(value, { stream:true });
                const lines = buf.split('\n\n'); buf = lines.pop() || '';
                for (const l of lines) { if (l.startsWith('data: ')) { const t = l.slice(6); if (t==='[DONE]') return; if (t.startsWith('[ERROR]')) { td.textContent += t.slice(8); return; } td.textContent += t; } }
            }
        } catch (err) { td.textContent = `Request failed: ${err.message}`; }
    },

    _addChatMsg(role, content) {
        const msgs = document.getElementById('chat-messages'); const w = msgs.querySelector('.chat-welcome'); if (w) w.remove();
        const d = document.createElement('div'); d.className = `chat-msg ${role}`;
        d.innerHTML = `<div class="chat-text">${content||''}</div>`;
        msgs.appendChild(d); msgs.scrollTop = msgs.scrollHeight; return d;
    },

    // ================================================================
    // New Project Form
    // ================================================================
    // Project creation is handled when the research form is opened.
    _setupFormHandlers() {
        // No setup needed — the old modal form has been removed.
        // Projects are created when the research form is opened.
    },

    _updateApiStatus(c) {
        const el = document.getElementById('api-status'); if (!el) return;
        if (c===undefined) { fetch('/api/projects').then(()=>{el.className='status-dot online';}).catch(()=>{el.className='status-dot offline';}); }
        else { el.className = c ? 'status-dot online' : 'status-dot offline'; }
    },
    _esc(s) { return Components._esc(s); },

    // ================================================================
    // Research import — creates a draft project if needed
    // ================================================================
    async startScan() {
        // 1. Auto-create draft project if needed
        if (!this.currentProjectId) {
            const draftConfig = {
                title: 'Untitled Project',
                inspiration: 'To be decided',
                genre: ['To be decided'],
                target_readers: 'Web fiction readers',
                tone: '',
                target_length: 'novel',
                target_word_count: 80000,
                style_reference: null,
                taboo_content: [],
                language: 'en',
                special_requirements: [],
            };
            try {
                const result = await API.createProject(draftConfig);
                await this._refreshProjects();
                this.currentProjectId = result.project_id;
                this._connectWS(result.project_id);
                this._initPipeline();
                this._showProjectHeader('Untitled Project');
            } catch (err) { alert(`Could not create project: ${err.message}`); return; }
        }

        this._navigate('workspace');
        document.getElementById('btn-start-scan').style.display = 'none';
        document.getElementById('scan-input-area').style.display = 'block';
        document.getElementById('scan-csv').focus();
    },

    /** Show project header in workspace */
    _showProjectHeader(title) {
        document.getElementById('workspace-default-title').style.display = 'none';
        document.getElementById('workspace-project-header').style.display = 'flex';
        document.getElementById('project-title-display').textContent = title;
    },

    /** Navigate to My Library */
    goToLibrary() {
        this._navigate('my-works');
    },

    // ================================================================
    // Topic Selection
    // ================================================================
    _selectedTopic: null,

    selectTopic(genreName) {
        this._selectedTopic = genreName;
        document.querySelectorAll('.topic-select-item').forEach(el => {
            el.classList.toggle('selected', el.dataset.genre === genreName);
        });
        // Auto-fill the editable title
        const titleData = this._topicTitleData?.find(t => t.genre_name === genreName);
        const titleInput = document.getElementById('topic-edit-title');
        if (titleInput) {
            titleInput.value = titleData?.final_title || genreName;
        }
    },

    async confirmTopic() {
        // Get selected synopsis card or fall back to checked topic
        let newTitle, genreName, synopsis;
        const insp = document.getElementById('topic-inspiration')?.value || '';

        if (this._selectedSynopsisIdx >= 0 && this._synopsisCards[this._selectedSynopsisIdx]) {
            const card = this._synopsisCards[this._selectedSynopsisIdx];
            newTitle = card.editedTitle || card.title;
            synopsis = card.editedSynopsis || card.synopsis;
            genreName = card.genreName;
        } else {
            // No synopsis card selected — use first checked candidate
            const checked = Object.entries(this._checkedCandidates || {}).filter(([_,v]) => v).map(([k]) => k);
            if (!checked.length) { alert('Select concepts and generate synopses, then choose a title.'); return; }
            genreName = checked[0];
            newTitle = genreName;
        }

        try {
            await API.updateTitle(this.currentProjectId, newTitle);
            await this._refreshProjects();
            this._showProjectHeader(newTitle);

            document.getElementById('topic-confirm-area').style.display = 'none';
            this._updatePipelineBadge('topic', 'done');
            this._updatePipelineBadge('arc', 'active');

            await API.confirmPhase(this.currentProjectId, insp || null, {
                genre_name: genreName, selected_title: synopsis ? newTitle : null, selected_synopsis: synopsis
            });
        } catch (err) { alert(`Confirmation failed: ${err.message}`); }
    },

    // ================================================================
    // Generic Step Confirmation (arc, bible, chars, outline)
    // ================================================================
    async confirmStep(step) {
        if (!this.currentProjectId) return;
        const inspEl = document.getElementById(`${step}-inspiration`);
        const insp = inspEl?.value || '';
        const nextMap = { arc:'bible', bible:'chars', chars:'outline', outline:'write' };
        try {
            await API.confirmPhase(this.currentProjectId, insp || null);
            this._updatePipelineBadge(step, 'done');
            if (nextMap[step]) this._updatePipelineBadge(nextMap[step], 'active');
            // Hide confirm bar
            const confirmEl = document.getElementById(`${step}-confirm-area`);
            if (confirmEl) confirmEl.style.display = 'none';
        } catch (err) { alert(`Confirmation failed: ${err.message}`); }
    },

    /** Retry a failed phase (e.g. mini_arc_outline). */
    async retryPhase(phase) {
        if (!this.currentProjectId) return;
        // Handle topic_selection UI reset
        if (phase === 'topic_selection') {
            document.getElementById('topic-candidates-area').style.display = 'none';
            document.getElementById('topic-synopsis-cards').style.display = 'none';
            document.getElementById('topic-confirm-area').style.display = 'none';
            const aiArea = document.getElementById('topic-ai-area');
            if (aiArea) {
                aiArea.style.display = 'block';
                aiArea.querySelector('p').innerHTML = '<span style="color:var(--accent)">🔄 Regenerating concepts. This may take a minute or two...</span>';
            }
            this._updatePipelineBadge('topic', 'running');
        }
        const resultEl = document.getElementById(`${phase === 'mini_arc_outline' ? 'arc' : phase}-result-area`);
        if (resultEl) resultEl.innerHTML = '<p style="color:var(--accent)">🔄 Regenerating...</p>';
        // Pick up any inspiration the user added
        const inspEl = document.getElementById(`${phase === 'mini_arc_outline' ? 'arc' : phase}-inspiration`);
        const insp = inspEl?.value?.trim() || '';
        try {
            await API.retryPhase(this.currentProjectId, phase, insp || null);
        } catch (err) {
            alert(`Retry failed: ${err.message}`);
        }
    },
};

document.addEventListener('DOMContentLoaded', () => App.init());
