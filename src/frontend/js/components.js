/**
 * UI component renderers — English display labels, no raw JSON/enum markers
 */
const Components = {
    ROLE: { protagonist:'Protagonist', antagonist:'Antagonist', deuteragonist:'Deuteragonist', supporting:'Supporting Character', minor:'Minor Character', mentor:'Mentor', love_interest:'Love Interest', rival:'Rival', foil:'Foil' },
    CONFLICT: {
        person_vs_person:'Person vs. Person', person_vs_society:'Person vs. Society', person_vs_self:'Person vs. Self',
        person_vs_nature:'Person vs. Nature', person_vs_technology:'Person vs. Technology', person_vs_faction:'Faction Conflict',
        person_vs_organisation:'Faction Conflict', person_vs_organization:'Faction Conflict',
        person_vs_destiny:'Person vs. Fate', person_vs_fate:'Person vs. Fate',
    },
    TURNING: { inciting_incident:'Inciting Incident', first_plot_point:'First Plot Point', midpoint:'Midpoint', all_is_lost:'All Is Lost', dark_night_of_soul:'Dark Night of the Soul', climax:'Climax', denouement:'Denouement' },
    SEVERITY: { critical:'Critical', major:'Major', minor:'Minor', suggestion:'Suggestion' },
    ARC: { main:'Main Plot', subplot:'Subplot', b_plot:'Secondary Plot' },
    TONE: { dark:'Dark', light:'Light', gritty:'Gritty', whimsical:'Whimsical', epic:'Epic' },
    SENTENCE: { varied:'Varied', simple:'Simple', ornate:'Ornate', minimalist:'Minimalist', complex:'Complex', balanced:'Balanced' },
    PACING: { fast:'Fast', medium:'Medium', slow:'Slow', 'medium-slow':'Moderately Slow', 'medium-fast':'Moderately Fast', variable:'Variable' },
    NARRATIVE: { close:'Close', distant:'Distant', omniscient:'Omniscient', 'third_person_limited':'Third-Person Limited' },
    ARCHETYPE: { hero:'Hero', mentor:'Mentor', herald:'Herald', trickster:'Trickster', shadow:'Shadow', 'threshold_guardian':'Threshold Guardian', shapeshifter:'Shapeshifter', ally:'Ally', 'anti_hero':'Antihero', villain:'Antagonist', sage:'Sage', explorer:'Explorer', rebel:'Rebel', lover:'Lover', creator:'Creator', ruler:'Ruler', everyman:'Everyman', caregiver:'Caregiver', innocent:'Innocent', jester:'Jester', orphan:'Orphan', warrior:'Warrior', magician:'Magician', seeker:'Seeker', destroyer:'Destroyer' },

    /** Universal label lookup: try map first, then humanize snake_case, else return as-is */
    _L(map, key) {
        if (!key) return '';
        if (map[key]) return map[key];
        // Try common variations
        const lower = String(key).toLowerCase().replace(/[ -]/g, '_');
        if (map[lower]) return map[lower];
        // Auto-humanize: person_vs_organisation → Person Vs Organisation
        if (/^[a-z][a-z_]+$/.test(key)) {
            return String(key).split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
        }
        return key;
    },

    _cleanJson(s) {
        if (!s || !s.startsWith('{')) return this._esc(s||'');
        try { const o = JSON.parse(s); return [o.name, o.rules, o.description, o.power_progression ? 'Progression: '+o.power_progression : ''].filter(Boolean).map(x=>this._esc(x)).join('<br>'); }
        catch(e) { return this._esc(s); }
    },

    /** Wraps a section with an edit/save toggle */
    _editableSection(id, title, contentHtml, textValue) {
        return `<div class="section editable-section" id="${id}-section">
            <div class="section-header"><h4>${title}</h4><button class="btn btn-secondary btn-sm" id="${id}-edit-btn" onclick="App.toggleEdit('${id}')">Edit</button></div>
            <div id="${id}-display">${contentHtml}</div>
            <div id="${id}-editor" style="display:none"><textarea style="width:100%;min-height:120px;padding:10px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text-primary);font-family:inherit;font-size:0.9rem;line-height:1.6;resize:vertical">${this._esc(textValue||'')}</textarea></div>
        </div>`;
    },

    overviewEditable(p) {
        if (!p?.config) return '<p>Loading...</p>';
        const c = p.config;
        const content = `<p>Title: ${this._esc(c.title||'Unset')}</p>
            <p>Inspiration: ${this._esc(c.inspiration||'')}</p>
            <p>Genre: ${(c.genre||[]).join(', ')}</p>
            <p>Target Readers: ${this._esc(c.target_readers||'')}</p>
            <p>Tone: ${this.TONE[c.tone]||c.tone||'Unspecified'}</p>
            <p>Length: ${c.target_length||'Unspecified'} (about ${(c.target_word_count||0).toLocaleString()} words)</p>
            ${c.style_reference?`<p>Style Reference: ${this._esc(c.style_reference)}</p>`:''}`;
        return this._editableSection('overview-basic', 'Project Basics', content, content.replace(/<[^>]+>/g,''));
    },

    bibleEditable(bible) {
        if (!bible) return '<p>Worldbuilding is pending.</p>';
        const w = bible.world||{}, s = bible.style_contract||{};
        const themes = bible.themes||[], factions = bible.factions||[], conflicts = bible.core_conflicts||[];
        let html = '';

        // World
        let worldHtml = '';
        if (w.geography) worldHtml += `<p><strong>Geography:</strong> ${this._esc(w.geography)}</p>`;
        if (w.history) worldHtml += `<p><strong>History:</strong> ${this._esc(w.history)}</p>`;
        if (w.culture) worldHtml += `<p><strong>Culture:</strong> ${this._esc(w.culture)}</p>`;
        if (w.technology_level) worldHtml += `<p><strong>Technology or Magic Level:</strong> ${this._esc(w.technology_level)}</p>`;
        if (w.magic_system) worldHtml += `<div class="highlight-box"><strong>Power System:</strong><br>${this._cleanJson(w.magic_system)}</div>`;
        if (w.power_progression) worldHtml += `<p><strong>Progression:</strong> ${this._cleanJson(w.power_progression)}</p>`;
        if (w.special_rules?.length) worldHtml += `<p><strong>Special Rules:</strong> ${w.special_rules.map(r=>this._esc(r)).join('; ')}</p>`;
        html += this._editableSection('bible-world', `World: ${this._esc(w.name||'Untitled')} (${w.world_type||''})`, worldHtml, worldHtml.replace(/<[^>]+>/g,''));
        if (factions.length) html += this._editableSection('bible-factions', `Factions (${factions.length})`, factions.map(f=>`<div class="char-card"><span class="char-name">${this._esc(f.name)}</span><span class="char-role">${this._esc(f.faction_type||'Organization')}</span>${f.goal?`<p>${this._esc(f.goal)}</p>`:''}</div>`).join(''), JSON.stringify(factions,null,2));
        html += this._editableSection('bible-style', 'Style Guide', `<p>Tone: ${this._L(this.TONE, s.tone)||'Unspecified'} / Sentence Style: ${this._L(this.SENTENCE, s.sentence_style)} / Pacing: ${this._L(this.PACING, s.pacing_preference)} / Narrative Distance: ${this._L(this.NARRATIVE, s.narrative_distance)}</p>`, JSON.stringify(s,null,2));
        if (themes.length) html += this._editableSection('bible-themes', `Themes (${themes.length})`, themes.map(t=>`<p><strong>${this._esc(t.name)}:</strong> ${this._esc(t.description||t.manifestation||'')}</p>`).join(''), JSON.stringify(themes,null,2));
        if (conflicts.length) html += this._editableSection('bible-conflicts', `Central Conflicts (${conflicts.length})`, conflicts.map(c=>`<p><strong>${this._L(this.CONFLICT, c.conflict_type)}:</strong> ${this._esc(c.description||'')}${c.stakes?` (Stakes: ${this._esc(c.stakes)})`:''}</p>`).join(''), JSON.stringify(conflicts,null,2));
        return html;
    },

    charactersEditable(chars) {
        if (!chars?.characters) return '<p>No characters yet.</p>';
        const list = Object.values(chars.characters);
        if (!list.length) return '<p>No characters yet.</p>';
        return list.map((c,i) => {
            let cardHtml = '';
            if (c.archetype&&c.archetype!=='None') cardHtml += `<p>Archetype: ${this._L(this.ARCHETYPE, c.archetype)}</p>`;
            cardHtml += `<p>Age: ${c.age||'Unknown'}${c.gender?` / ${this._esc(c.gender)}`:''}</p>`;
            if (c.personality) cardHtml += `<p>Personality: ${this._esc(c.personality)}</p>`;
            if (c.motivation) cardHtml += `<p>Motivation: ${this._esc(c.motivation)}</p>`;
            if (c.flaw) cardHtml += `<p>Flaw: ${this._esc(c.flaw)}</p>`;
            if (c.backstory) cardHtml += `<p>Backstory: ${this._esc(String(c.backstory).substring(0,300))}</p>`;
            if (c.abilities?.length) cardHtml += `<p>Abilities: ${c.abilities.map(a=>this._esc(String(a))).join(', ')}</p>`;
            return this._editableSection(`char-${i}`, c.name, cardHtml, JSON.stringify(c,null,2));
        }).join('');
    },

    outlineEditable(outline) {
        if (!outline) return '<p>No outline yet.</p>';
        const vols = outline.volumes||[], tps = outline.major_turning_points||[];
        const main = outline.main_plot||[], subs = outline.subplots||[];
        let html = '';
        html += this._editableSection('outline-info', 'Project Basics', `<p>${this._esc(outline.logline||'')}</p><p>Planned Chapters: ${outline.chapter_count||'To be decided'}</p>`, JSON.stringify({logline:outline.logline,chapter_count:outline.chapter_count},null,2));
        if (main.length) html += this._editableSection('outline-main', 'Main Plot', main.map(a=>`<p><strong>${this._esc(a.name)}</strong>${a.description?`: ${this._esc(a.description)}`:''}</p>`).join(''), JSON.stringify(main,null,2));
        if (subs.length) html += this._editableSection('outline-subs', 'Subplot', subs.map(a=>`<p><strong>${this._esc(a.name)}</strong>${a.description?`: ${this._esc(a.description)}`:''}</p>`).join(''), JSON.stringify(subs,null,2));
        if (vols.length) html += this._editableSection('outline-vols', `Volumes (${vols.length})`, vols.map((v,i)=>{const n=v.number||i+1;return`<p><strong>Volume ${n}: ${this._esc(v.title)}</strong> (Chapters ${v.start_chapter||'?'}-${v.end_chapter||'?'})${v.logline?` — ${this._esc(v.logline)}`:''}</p>`;}).join(''), JSON.stringify(vols,null,2));
        if (tps.length) html += this._editableSection('outline-tps', 'Key Turning Points', tps.map(tp=>`<p><strong>${this._L(this.TURNING, tp.turning_type)} (Chapter ${tp.chapter||'?'}):</strong> ${this._esc(tp.description||'')}</p>`).join(''), JSON.stringify(tps,null,2));
        return html;
    },

    projectOverview(p) {
        if (!p?.config) return '<p>Loading...</p>';
        const c = p.config;
        return `<div class="section"><h4>Project Basics</h4>
            <p><strong>Title:</strong> ${this._esc(c.title||'Unset')}</p>
            <p><strong>Inspiration:</strong> ${this._esc(c.inspiration||'')}</p>
            <p><strong>Genre:</strong> ${(c.genre||[]).join(', ')}</p>
            <p><strong>Target Readers:</strong> ${this._esc(c.target_readers||'')}</p>
            <p><strong>Tone:</strong> ${this.TONE[c.tone]||c.tone||'Unspecified'}</p>
            <p><strong>Length:</strong> ${c.target_length||'Unspecified'} (about ${(c.target_word_count||0).toLocaleString()} words)</p>
            ${c.style_reference ? `<p><strong>Style Reference:</strong> ${this._esc(c.style_reference)}</p>` : ''}
        </div>`;
    },

    bibleView(bible) {
        if (!bible) return '<p>Worldbuilding is pending.</p>';
        const w = bible.world||{}, s = bible.style_contract||{};
        const themes = bible.themes||[], factions = bible.factions||[], conflicts = bible.core_conflicts||[];
        return `<div class="section"><h4>World: ${this._esc(w.name||'Untitled')} (${w.world_type||''})</h4>
            ${w.geography?`<p><strong>Geography:</strong> ${this._esc(w.geography)}</p>`:''}
            ${w.history?`<p><strong>History:</strong> ${this._esc(w.history)}</p>`:''}
            ${w.culture?`<p><strong>Culture:</strong> ${this._esc(w.culture)}</p>`:''}
            ${w.technology_level?`<p><strong>Technology or Magic Level:</strong> ${this._esc(w.technology_level)}</p>`:''}
            ${w.magic_system?`<div class="highlight-box"><strong>Power System:</strong><br>${this._cleanJson(w.magic_system)}</div>`:''}
            ${w.power_progression?`<p><strong>Progression:</strong> ${this._cleanJson(w.power_progression)}</p>`:''}
            ${w.special_rules?.length?`<p><strong>Special Rules:</strong> ${w.special_rules.map(r=>this._esc(r)).join('; ')}</p>`:''}
        </div>
        ${factions.length?`<div class="section"><h4>Factions (${factions.length})</h4>${factions.map(f=>`<div class="char-card"><span class="char-name">${this._esc(f.name)}</span><span class="char-role">${this._esc(f.faction_type||'Organization')}</span>${f.goal?`<p>${this._esc(f.goal)}</p>`:''}${f.ideology?`<p>Ideology: ${this._esc(f.ideology)}</p>`:''}</div>`).join('')}</div>`:''}
        <div class="section"><h4>Style Guide</h4><p>Tone: ${this._L(this.TONE, s.tone)||'Unspecified'} / Sentence Style: ${this._L(this.SENTENCE, s.sentence_style)} / Pacing: ${this._L(this.PACING, s.pacing_preference)} / Narrative Distance: ${this._L(this.NARRATIVE, s.narrative_distance)}</p>${s.preferred_techniques?.length?`<p>Techniques: ${s.preferred_techniques.join(', ')}</p>`:''}</div>
        ${themes.length?`<div class="section"><h4>Themes (${themes.length})</h4>${themes.map(t=>`<div class="char-card"><span class="char-name">${this._esc(t.name)}</span><p>${this._esc(t.description||t.manifestation||'')}</p></div>`).join('')}</div>`:''}
        ${conflicts.length?`<div class="section"><h4>Central Conflicts (${conflicts.length})</h4>${conflicts.map(c=>`<div class="char-card"><span class="char-name">${this._L(this.CONFLICT, c.conflict_type)}</span><p>${this._esc(c.description||'')}</p>${c.stakes?`<p>Stakes: ${this._esc(c.stakes)}</p>`:''}</div>`).join('')}</div>`:''}`;
    },

    charactersView(chars) {
        if (!chars?.characters) return '<p>No characters yet.</p>';
        const list = Object.values(chars.characters);
        if (!list.length) return '<p>No characters yet.</p>';
        return list.map(c => `<div class="char-card">
            <h4>${this._esc(c.name)}</h4>
            ${c.archetype&&c.archetype!=='None'?`<p>Archetype: ${this._L(this.ARCHETYPE, c.archetype)}</p>`:''}
            <p>Age: ${c.age||'Unknown'}${c.gender?` / ${this._esc(c.gender)}`:''}</p>
            ${c.personality?`<p>Personality: ${this._esc(c.personality)}</p>`:''}
            ${c.motivation?`<p>Motivation: ${this._esc(c.motivation)}</p>`:''}
            ${c.flaw?`<p>Flaw: ${this._esc(c.flaw)}</p>`:''}
            ${c.backstory?`<p>Backstory: ${this._esc(String(c.backstory).substring(0,300))}</p>`:''}
            ${c.abilities?.length?`<p>Abilities: ${c.abilities.map(a=>this._esc(String(a))).join(', ')}</p>`:''}
        </div>`).join('');
    },

    outlineView(outline) {
        if (!outline) return '<p>No outline yet.</p>';
        const vols = outline.volumes||[], tps = outline.major_turning_points||[];
        const main = outline.main_plot||[], subs = outline.subplots||[];
        return `<div class="section"><h4>${this._esc(outline.title||'Untitled')}</h4>${outline.logline?`<p>${this._esc(outline.logline)}</p>`:''}<p>Planned Chapters: ${outline.chapter_count||'To be decided'}</p></div>
        ${main.length?`<div class="section"><h4>Main Plot</h4>${main.map(a=>`<div class="char-card"><strong>${this._esc(a.name)}</strong>${a.description?`: ${this._esc(a.description)}`:''}</div>`).join('')}</div>`:''}
        ${subs.length?`<div class="section"><h4>Subplot</h4>${subs.map(a=>`<div class="char-card"><strong>${this._esc(a.name)}</strong>${a.description?`: ${this._esc(a.description)}`:''}</div>`).join('')}</div>`:''}
        ${vols.length?`<div class="section"><h4>Volumes (${vols.length})</h4>${vols.map((v,i)=>{const n=v.number||i+1;return`<div class="char-card"><span class="char-name">Volume ${n}: ${this._esc(v.title)}</span><p>Chapters ${v.start_chapter||'?'}-${v.end_chapter||'?'}</p>${v.logline?`<p>${this._esc(v.logline)}</p>`:''}${v.emotional_arc?`<p>Emotional Arc: ${this._esc(v.emotional_arc)}</p>`:''}</div>`;}).join('')}</div>`:''}
        ${tps.length?`<div class="section"><h4>Key Turning Points</h4>${tps.map(tp=>`<div class="char-card"><span class="char-name">${this._L(this.TURNING, tp.turning_type)}</span><span class="char-role">Chapter ${tp.chapter||'?'}</span><p>${this._esc(tp.description||'')}</p></div>`).join('')}</div>`:''}`;
    },

    _STATUS: { planned:'Planned', writing:'Writing', reviewing:'Reviewing', polishing:'Polishing', done:'Complete', initialized:'Not started' },

    chaptersView(chapters, opts) {
        const hasChapters = chapters && chapters.length;
        const { workflowDone, totalChapters } = opts || {};
        const allDone = workflowDone;
        const partial = hasChapters && !allDone;
        let html = '';
        if (!hasChapters) {
            html += '<p>No chapters yet.</p>';
            html += `<div class="section"><button class="btn btn-primary btn-lg" onclick="App.startWorkflow()">Start Writing</button></div>`;
        } else {
            html += chapters.map(ch => {
                const num = ch.chapter_number || 0;
                const st = this._STATUS[ch.status] || ch.status || 'Not started';
                return `<div class="card" style="cursor:pointer">
                    <div onclick="App.viewChapter(${num})" style="flex:1">
                        <h3>Chapter ${num} ${this._esc(ch.title)}</h3>
                        <span class="status status-${ch.status||'initialized'}">${st}</span>
                    </div>
                    <button class="btn btn-error btn-sm" onclick="event.stopPropagation();App.deleteChapter(${num})" style="margin-left:8px;flex-shrink:0">Delete</button>
                </div>`;
            }).join('');
            if (partial) {
                const done = chapters.length;
                html += `<div class="section" style="margin-top:12px"><p>Chapters completed: ${done}${totalChapters ? ' / '+totalChapters : ''}</p><button class="btn btn-primary" onclick="App.startWorkflow()">Continue Writing</button></div>`;
            }
        }
        if (allDone) {
            html += `<div class="section" style="margin-top:16px"><h4>Export As</h4><div style="display:flex;gap:8px"><button class="btn btn-secondary btn-sm" onclick="App.exportDocx()">DOCX</button><button class="btn btn-secondary btn-sm" onclick="App.exportMarkdown()">Markdown</button></div></div>`;
        }
        return html;
    },

    reviewScores(scores) {
        if (!scores) return '';
        const labels = { consistency:'Consistency', character:'Characters', pacing:'Pacing', hook:'Hook', style:'Style', ai_flavor:'Naturalness', reader_engagement:'Reader Engagement', continuation_likelihood:'Likelihood of Continuing' };
        return `<div class="score-grid">${Object.entries(scores).map(([k,v])=>`<div class="score-item"><div class="score-value">${Number(v).toFixed(1)}</div><div class="score-label">${labels[k]||k}</div></div>`).join('')}</div>`;
    },

    issuesList(issues) {
        if (!issues?.length) return '<p>No issues.</p>';
        return issues.map(i => `<div class="issue ${i.severity||''}"><span class="severity-tag ${i.severity||''}">${this._L(this.SEVERITY, i.severity)||'Note'}</span>${i.description?this._esc(i.description):''}${i.suggestion?`<br><em>Suggestion: ${this._esc(i.suggestion)}</em>`:''}</div>`).join('');
    },

    phaseConfirmPanel(phase) {
        const labels = { platform_scan:'Research Snapshots', topic_selection:'Topic Research', mini_arc_outline:'Opening Arc Outline', bible_construction:'Worldbuilding', character_creation:'Character Creation', master_outline:'Outline Generation', chapter_planning:'Chapter Planning', chapter_writing:'Chapter Writing' };
        const hints = { platform_scan:'Review the snapshot coverage before moving on to topic research.', topic_selection:'Confirm the concept to generate the opening arc outline.', mini_arc_outline:'Confirm the outline to start worldbuilding.', bible_construction:'Review the worldbuilding before creating characters.', character_creation:'Review the characters before generating the outline.', master_outline:'Confirm the outline to start writing chapters.' };
        const label = labels[phase]||phase;
        return `<div class="confirm-panel phase-confirm" data-phase="${phase}"><h3>${label} complete</h3><p>${hints[phase]||'Confirm to continue.'}</p>
            <div class="form-group"><label>Additional Ideas (Optional)</label><textarea id="inspiration-input" placeholder="Add your ideas..." style="width:100%;padding:10px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text-primary);min-height:60px;font-family:inherit;font-size:0.9rem;"></textarea></div>
            <div class="confirm-actions"><button class="btn btn-success" onclick="App.confirmPhase()">Confirm and Continue</button></div></div>`;
    },

    confirmPanel(chapterNumber, review) {
        return `<div class="confirm-panel"><h3>Chapter ${chapterNumber} Review Complete</h3>
            ${review?`<p>Overall Score: <strong>${Number(review.overall_score).toFixed(1)}/10</strong></p>${this.reviewScores(review.dimension_scores)}<h4 style="margin-top:16px">Issues (${review.issues?.length||0})</h4>${this.issuesList(review.issues)}`:''}
            <div class="confirm-actions"><button class="btn btn-success" onclick="App.confirmDecision('accept')">Accept</button><button class="btn btn-warning" onclick="App.confirmDecision('revise')">Revise</button><button class="btn btn-error" onclick="App.confirmDecision('rewrite')">Rewrite</button></div>
            <div style="margin-top:12px"><textarea id="feedback-input" placeholder="Revision feedback..." style="width:100%;padding:10px;background:var(--bg-input);border:1px solid var(--border);border-radius:6px;color:var(--text-primary);min-height:60px"></textarea></div></div>`;
    },

    topicResearchView() {
        return `<div class="section">
            <p>Record dated list observations from Wattpad or Royal Road.</p>
            <button class="btn btn-primary" onclick="App.startScan()">Import Research</button>
        </div>`;
    },

    _esc(s) {
        if (!s) return '';
        return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    },
};
