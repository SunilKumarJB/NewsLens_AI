// State Management
let articlesList = [];
let selectedFile = null;

// API Base Endpoints
const API_URLS = {
    getArticles: '/api/articles',
    search: '/api/search',
    upload: '/api/upload'
};

// DOM Elements
const DOM = {
    totalArticlesCount: document.getElementById('total-articles-count'),
    dragZone: document.getElementById('upload-drag-zone'),
    fileInput: document.getElementById('file-input'),
    fileInfoContainer: document.getElementById('file-info-container'),
    fileName: document.getElementById('selected-file-name'),
    fileSize: document.getElementById('selected-file-size'),
    btnSubmitProcess: document.getElementById('btn-submit-process'),
    
    // GCS Tab elements
    tabLocal: document.getElementById('tab-local'),
    tabGcs: document.getElementById('tab-gcs'),
    gcsInputContainer: document.getElementById('gcs-input-container'),
    gcsPathInput: document.getElementById('gcs-path-input'),
    btnSubmitGcs: document.getElementById('btn-submit-gcs'),
    
    pipelineProgressContainer: document.getElementById('pipeline-progress-container'),
    progressIndicatorBar: document.getElementById('progress-indicator-bar'),
    stepExtract: document.getElementById('step-extract'),
    stepMetadata: document.getElementById('step-metadata'),
    stepEmbeddings: document.getElementById('step-embeddings'),
    stepSave: document.getElementById('step-save'),
    
    searchForm: document.getElementById('search-form'),
    searchInput: document.getElementById('search-input'),
    searchResultsInfoBar: document.getElementById('search-results-info-bar'),
    searchResultsCountText: document.getElementById('search-results-count-text'),
    btnClearSearch: document.getElementById('btn-clear-search'),
    
    articlesGrid: document.getElementById('articles-feed-grid'),
    
    // Modal Detail View
    detailModal: document.getElementById('article-detail-modal'),
    modalCloseBtn: document.getElementById('modal-close-btn'),
    modalPageNum: document.getElementById('modal-page-num'),
    modalAuthor: document.getElementById('modal-author'),
    modalHeadline: document.getElementById('modal-headline'),
    modalSubheadline: document.getElementById('modal-subheadline'),
    modalBodyText: document.getElementById('modal-body-text'),
    modalMetaDesc: document.getElementById('modal-meta-desc'),
    modalSummary: document.getElementById('modal-summary'),
    modalPrimaryKeyword: document.getElementById('modal-primary-keyword'),
    modalSecondaryKeywords: document.getElementById('modal-secondary-keywords'),
    modalTags: document.getElementById('modal-tags'),
    
    // Insight Block containers (for hiding empty blocks)
    modalMetaDescBlock: document.getElementById('modal-meta-desc-block'),
    modalSummaryBlock: document.getElementById('modal-summary-block'),
    modalPrimaryKeywordBlock: document.getElementById('modal-primary-keyword-block'),
    modalSecondaryKeywordsBlock: document.getElementById('modal-secondary-keywords-block'),
    modalTagsBlock: document.getElementById('modal-tags-block'),
    
    // Global Tab Navigation Views
    dashboardView: document.getElementById('dashboard-view'),
    architectView: document.getElementById('architect-view'),
    navTabDashboard: document.getElementById('nav-tab-dashboard'),
    navTabArchitect: document.getElementById('nav-tab-architect'),
    
    // Layout Architect Elements
    architectChecklistContainer: document.getElementById('architect-checklist-container'),
    btnGenerateEditorial: document.getElementById('btn-generate-editorial'),
    architectCanvas: document.getElementById('architect-canvas'),
    btnDownloadHtml: document.getElementById('btn-download-html'),
    btnPrintLayout: document.getElementById('btn-print-layout'),
    iframeWrapper: document.querySelector('.iframe-wrapper')
};

// Global generated layout state variable
let generatedLayoutHtml = "";

// --- Initialize App ---
document.addEventListener('DOMContentLoaded', () => {
    fetchArticles();
    setupUploadEvents();
    setupSearchEvents();
    setupModalEvents();
    setupArchitectEvents();
    
    // Initialize automatic background sync with backend database
    setInterval(syncArticlesSilent, 10000);
});

// --- Fetch Articles from Local Backend ---
async function fetchArticles() {
    try {
        showShimmers();
        const response = await fetch(API_URLS.getArticles);
        const result = await response.json();
        
        if (result.status === 'success') {
            articlesList = result.data;
            renderArticles(articlesList);
            DOM.totalArticlesCount.textContent = articlesList.length;
        } else {
            showErrorCard("Failed to load articles.");
        }
    } catch (error) {
        console.error("Error fetching articles:", error);
        showErrorCard("Unable to connect to backend server. Please start the FastAPI service.");
    }
}

// --- Background Silent Sync for Real-time Updates ---
async function syncArticlesSilent() {
    try {
        const response = await fetch(API_URLS.getArticles);
        const result = await response.json();
        
        if (result.status === 'success') {
            const newArticles = result.data;
            const currentTopId = articlesList.length > 0 ? articlesList[0].article_id : null;
            const newTopId = newArticles.length > 0 ? newArticles[0].article_id : null;
            const changed = (articlesList.length !== newArticles.length) || (currentTopId !== newTopId);
            
            articlesList = newArticles;
            DOM.totalArticlesCount.textContent = articlesList.length;
            
            if (changed) {
                // Only re-render grid if search is not active and we are in dashboard view
                if (DOM.searchResultsInfoBar.classList.contains('hidden') && !DOM.dashboardView.classList.contains('hidden')) {
                    renderArticles(articlesList);
                }
                // If architect view is active, update checklist but preserve checked state
                if (!DOM.architectView.classList.contains('hidden')) {
                    const checkedBoxes = Array.from(DOM.architectChecklistContainer.querySelectorAll('.checklist-checkbox:checked')).map(b => b.value);
                    renderArchitectChecklist();
                    checkedBoxes.forEach(val => {
                        const box = DOM.architectChecklistContainer.querySelector(`.checklist-checkbox[value="${val}"]`);
                        if (box) box.checked = true;
                    });
                }
            }
        }
    } catch (error) {
        console.error("Error syncing articles:", error);
    }
}

// --- Render Articles in Dashboard Grid ---
function renderArticles(articles, showScore = false) {
    DOM.articlesGrid.innerHTML = '';
    
    if (articles.length === 0) {
        DOM.articlesGrid.innerHTML = `
            <div class="glass-panel" style="grid-column: 1 / -1; text-align: center; padding: 3rem;">
                <h3 style="margin-bottom: 10px;">No Articles Found</h3>
                <p style="color: var(--text-muted);">Try uploading a new newspaper PDF or updating your search query.</p>
            </div>
        `;
        return;
    }
    
    articles.forEach(article => {
        const card = document.createElement('div');
        card.className = 'article-card';
        
        // Add Similarity Score Badge if this is search view
        let scoreBadgeHtml = '';
        if (showScore && article.similarity_score !== undefined) {
            const scorePercent = (article.similarity_score * 100).toFixed(1);
            scoreBadgeHtml = `<span class="similarity-badge">Match: ${scorePercent}%</span>`;
        }
        
        // Parse secondary tags to show capsules
        const tagsHtml = (article.tags || []).slice(0, 3).map(tag => 
            `<span class="tag-badge">${tag}</span>`
        ).join('');
        
        card.innerHTML = `
            ${scoreBadgeHtml}
            <div class="card-top-info">
                <span class="page-badge">Page ${article.page_number || '1'}</span>
                <span class="author-badge">${article.dateline_or_author || 'Special Correspondent'}</span>
            </div>
            <h3 lang="hi">${article.headline}</h3>
            <p lang="hi">${article.summary || article.body_text}</p>
            <div class="card-footer">
                ${tagsHtml}
            </div>
        `;
        
        // Click event to open Detail Modal Overlay
        card.addEventListener('click', () => openDetailModal(article));
        
        DOM.articlesGrid.appendChild(card);
    });
}

// --- Helper to Show Shimmers ---
function showShimmers() {
    DOM.articlesGrid.innerHTML = `
        <div class="shimmer-card"></div>
        <div class="shimmer-card"></div>
        <div class="shimmer-card"></div>
    `;
}

// --- Helper to Show Error Message ---
function showErrorCard(message) {
    DOM.articlesGrid.innerHTML = `
        <div class="glass-panel" style="grid-column: 1 / -1; text-align: center; border-color: rgba(239,68,68,0.3); padding: 3rem;">
            <h3 style="color: #f87171; margin-bottom: 10px;">Error</h3>
            <p style="color: var(--text-secondary);">${message}</p>
        </div>
    `;
}

// --- Setup Upload Drag & Drop & Input ---
function setupUploadEvents() {
    // Drag and Drop listeners
    ['dragenter', 'dragover'].forEach(eventName => {
        DOM.dragZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            DOM.dragZone.style.borderColor = 'var(--accent-teal)';
            DOM.dragZone.style.background = 'rgba(6, 182, 212, 0.03)';
        }, false);
    });
    
    ['dragleave', 'drop'].forEach(eventName => {
        DOM.dragZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            DOM.dragZone.style.borderColor = 'var(--border-color)';
            DOM.dragZone.style.background = 'none';
        }, false);
    });
    
    DOM.dragZone.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files.length > 0 && files[0].type === 'application/pdf') {
            handleFileSelected(files[0]);
        }
    });
    
    // Click zone listeners
    DOM.dragZone.addEventListener('click', () => {
        DOM.fileInput.click();
    });
    
    DOM.fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleFileSelected(e.target.files[0]);
        }
    });
    
    // Start Processing Pipeline Button
    DOM.btnSubmitProcess.addEventListener('click', () => {
        if (selectedFile) {
            uploadAndProcessPDF(selectedFile);
        }
    });

    // Ingestion Type Tabs Toggle
    DOM.tabLocal.addEventListener('click', () => {
        DOM.tabLocal.classList.add('active');
        DOM.tabGcs.classList.remove('active');
        DOM.gcsInputContainer.classList.add('hidden');
        
        // Show local upload components depending on file selection state
        if (selectedFile) {
            DOM.fileInfoContainer.classList.remove('hidden');
        } else {
            DOM.dragZone.classList.remove('hidden');
        }
    });
    
    DOM.tabGcs.addEventListener('click', () => {
        DOM.tabGcs.classList.add('active');
        DOM.tabLocal.classList.remove('active');
        DOM.dragZone.classList.add('hidden');
        DOM.fileInfoContainer.classList.add('hidden');
        DOM.gcsInputContainer.classList.remove('hidden');
    });
    
    // Submit GCS Bucket Path Button
    DOM.btnSubmitGcs.addEventListener('click', () => {
        const gcsUri = DOM.gcsPathInput.value.trim();
        if (gcsUri) {
            processGcsPDF(gcsUri);
        } else {
            alert("Please enter a valid gs:// bucket path link.");
        }
    });
}

function handleFileSelected(file) {
    selectedFile = file;
    DOM.fileName.textContent = file.name;
    DOM.fileSize.textContent = (file.size / (1024 * 1024)).toFixed(2) + ' MB';
    
    DOM.dragZone.classList.add('hidden');
    DOM.fileInfoContainer.classList.remove('hidden');
}

// --- Upload and Process Newspaper PDF ---
async function uploadAndProcessPDF(file) {
    const formData = new FormData();
    formData.append('file', file);
    
    // UI State changes: Show progress panels
    DOM.pipelineProgressContainer.classList.remove('hidden');
    DOM.btnSubmitProcess.disabled = true;
    DOM.btnSubmitProcess.textContent = "AI analysis in progress...";
    DOM.btnSubmitProcess.style.opacity = "0.6";
    
    // Animate pipeline steps smoothly
    let progress = 0;
    const progressInterval = setInterval(() => {
        if (progress < 85) {
            progress += 1;
            DOM.progressIndicatorBar.style.width = progress + '%';
        }
    }, 350);
    
    // Step updates
    updateStepUI('extract', 'active');
    
    // Helper timeout to shift steps to look interactive
    const t1 = setTimeout(() => {
        updateStepUI('extract', 'completed');
        updateStepUI('metadata', 'active');
    }, 8000);
    
    const t2 = setTimeout(() => {
        updateStepUI('metadata', 'completed');
        updateStepUI('embeddings', 'active');
    }, 16000);
    
    const t3 = setTimeout(() => {
        updateStepUI('embeddings', 'completed');
        updateStepUI('save', 'active');
    }, 24000);

    try {
        const response = await fetch(API_URLS.upload, {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        
        clearInterval(progressInterval);
        clearTimeout(t1);
        clearTimeout(t2);
        clearTimeout(t3);
        
        if (result.status === 'success') {
            // Set 100% progress and active/completed styles
            DOM.progressIndicatorBar.style.width = '100%';
            updateStepUI('extract', 'completed');
            updateStepUI('metadata', 'completed');
            updateStepUI('embeddings', 'completed');
            updateStepUI('save', 'completed');
            
            setTimeout(() => {
                alert(`Success: ${result.message}`);
                resetUploadUI();
                fetchArticles();
            }, 1000);
        } else {
            alert(`Failed: ${result.detail || "Pipeline processing failed."}`);
            resetUploadUI();
        }
    } catch (error) {
        clearInterval(progressInterval);
        clearTimeout(t1);
        clearTimeout(t2);
        clearTimeout(t3);
        
        console.error("Upload error:", error);
        alert("Upload error: Connection to the server failed or file size exceeds limits.");
        resetUploadUI();
    }
}

function updateStepUI(stepName, state) {
    let stepEl = null;
    if (stepName === 'extract') stepEl = DOM.stepExtract;
    if (stepName === 'metadata') stepEl = DOM.stepMetadata;
    if (stepName === 'embeddings') stepEl = DOM.stepEmbeddings;
    if (stepName === 'save') stepEl = DOM.stepSave;
    
    if (stepEl) {
        stepEl.classList.remove('active', 'completed');
        stepEl.classList.add(state);
    }
}

// --- Process GCS Bucket Path PDF ---
async function processGcsPDF(gcsUri) {
    // UI State changes: Show progress panels
    DOM.pipelineProgressContainer.classList.remove('hidden');
    DOM.btnSubmitGcs.disabled = true;
    DOM.btnSubmitGcs.textContent = "AI analysis in progress...";
    DOM.btnSubmitGcs.style.opacity = "0.6";
    
    // Animate pipeline steps smoothly
    let progress = 0;
    const progressInterval = setInterval(() => {
        if (progress < 85) {
            progress += 1;
            DOM.progressIndicatorBar.style.width = progress + '%';
        }
    }, 350);
    
    // Step updates
    updateStepUI('extract', 'active');
    
    // Helper timeout to shift steps to look interactive
    const t1 = setTimeout(() => {
        updateStepUI('extract', 'completed');
        updateStepUI('metadata', 'active');
    }, 8000);
    
    const t2 = setTimeout(() => {
        updateStepUI('metadata', 'completed');
        updateStepUI('embeddings', 'active');
    }, 16000);
    
    const t3 = setTimeout(() => {
        updateStepUI('embeddings', 'completed');
        updateStepUI('save', 'active');
    }, 24000);

    try {
        const response = await fetch('/api/process-gcs', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ gcs_uri: gcsUri })
        });
        
        const result = await response.json();
        
        clearInterval(progressInterval);
        clearTimeout(t1);
        clearTimeout(t2);
        clearTimeout(t3);
        
        if (result.status === 'success') {
            // Set 100% progress and active/completed styles
            DOM.progressIndicatorBar.style.width = '100%';
            updateStepUI('extract', 'completed');
            updateStepUI('metadata', 'completed');
            updateStepUI('embeddings', 'completed');
            updateStepUI('save', 'completed');
            
            setTimeout(() => {
                alert(`Success: ${result.message}`);
                resetUploadUI();
                fetchArticles();
            }, 1000);
        } else {
            alert(`Failed: ${result.detail || "Pipeline GCS processing failed."}`);
            resetUploadUI();
        }
    } catch (error) {
        clearInterval(progressInterval);
        clearTimeout(t1);
        clearTimeout(t2);
        clearTimeout(t3);
        
        console.error("GCS upload error:", error);
        alert("GCS processing error: Connection to the server failed.");
        resetUploadUI();
    }
}

function resetUploadUI() {
    selectedFile = null;
    DOM.fileInput.value = '';
    DOM.gcsPathInput.value = '';
    
    // Reset Ingest tabs state
    DOM.tabLocal.classList.add('active');
    DOM.tabGcs.classList.remove('active');
    
    DOM.dragZone.classList.remove('hidden');
    DOM.fileInfoContainer.classList.add('hidden');
    DOM.gcsInputContainer.classList.add('hidden');
    
    DOM.pipelineProgressContainer.classList.add('hidden');
    DOM.progressIndicatorBar.style.width = '0%';
    
    // Reset step items
    [DOM.stepExtract, DOM.stepMetadata, DOM.stepEmbeddings, DOM.stepSave].forEach(el => {
        el.classList.remove('active', 'completed');
    });
    
    DOM.btnSubmitProcess.disabled = false;
    DOM.btnSubmitProcess.textContent = "Start AI Analysis";
    DOM.btnSubmitProcess.style.opacity = "1";
    
    DOM.btnSubmitGcs.disabled = false;
    DOM.btnSubmitGcs.textContent = "Analyze GCS Path";
    DOM.btnSubmitGcs.style.opacity = "1";
}

// --- Setup Vector Search Events ---
function setupSearchEvents() {
    DOM.searchForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const queryText = DOM.searchInput.value.trim();
        if (!queryText) return;
        
        try {
            showShimmers();
            DOM.searchResultsInfoBar.classList.remove('hidden');
            DOM.searchResultsCountText.textContent = `Searching for: "${queryText}"...`;
            
            const response = await fetch(API_URLS.search, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query: queryText, limit: 10 })
            });
            
            const result = await response.json();
            
            if (result.status === 'success') {
                renderArticles(result.data, true);
                DOM.searchResultsCountText.textContent = `Semantic search results for: "${queryText}" (${result.data.length} matches found)`;
            } else {
                showErrorCard("Search failed.");
            }
        } catch (error) {
            console.error("Search error:", error);
            showErrorCard("Failed to contact backend search server.");
        }
    });
    
    // Clear Search
    DOM.btnClearSearch.addEventListener('click', () => {
        DOM.searchInput.value = '';
        DOM.searchResultsInfoBar.classList.add('hidden');
        fetchArticles();
    });
}

// --- Modal Detail overlay handler ---
function setupModalEvents() {
    DOM.modalCloseBtn.addEventListener('click', closeModal);
    
    // Close modal when clicking outside the modal card
    DOM.detailModal.addEventListener('click', (e) => {
        if (e.target === DOM.detailModal) {
            closeModal();
        }
    });
    
    // Escape key closes modal
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !DOM.detailModal.classList.contains('hidden')) {
            closeModal();
        }
    });
}

function openDetailModal(article) {
    // Populate Modal Content fields
    DOM.modalPageNum.textContent = `Page ${article.page_number || '1'}`;
    DOM.modalAuthor.textContent = article.dateline_or_author || 'Special Correspondent';
    DOM.modalHeadline.textContent = article.headline;
    
    if (article.sub_headline) {
        DOM.modalSubheadline.textContent = article.sub_headline;
        DOM.modalSubheadline.classList.remove('hidden');
    } else {
        DOM.modalSubheadline.classList.add('hidden');
    }
    
    DOM.modalBodyText.textContent = article.body_text;
    
    // AI SEO Info population (dynamic hiding of empty blocks)
    if (article.meta_description && article.meta_description.trim()) {
        DOM.modalMetaDesc.textContent = article.meta_description;
        DOM.modalMetaDescBlock.classList.remove('hidden');
    } else {
        DOM.modalMetaDescBlock.classList.add('hidden');
    }
    
    if (article.summary && article.summary.trim()) {
        DOM.modalSummary.textContent = article.summary;
        DOM.modalSummaryBlock.classList.remove('hidden');
    } else {
        DOM.modalSummaryBlock.classList.add('hidden');
    }
    
    if (article.primary_keyword && article.primary_keyword.trim()) {
        DOM.modalPrimaryKeyword.textContent = article.primary_keyword;
        DOM.modalPrimaryKeywordBlock.classList.remove('hidden');
    } else {
        DOM.modalPrimaryKeywordBlock.classList.add('hidden');
    }
    
    // Populate Secondary keywords capsules
    const secKws = article.secondary_keywords || [];
    if (secKws.length > 0) {
        DOM.modalSecondaryKeywords.innerHTML = '';
        secKws.forEach(kw => {
            const pill = document.createElement('span');
            pill.className = 'keyword-pill secondary';
            pill.setAttribute('lang', 'hi'); // Support Devanagari font stack fallbacks
            pill.textContent = kw;
            DOM.modalSecondaryKeywords.appendChild(pill);
        });
        DOM.modalSecondaryKeywordsBlock.classList.remove('hidden');
    } else {
        DOM.modalSecondaryKeywordsBlock.classList.add('hidden');
    }
    
    // Populate Category/Tags capsules
    const tags = article.tags || [];
    if (tags.length > 0) {
        DOM.modalTags.innerHTML = '';
        tags.forEach(tag => {
            const badge = document.createElement('span');
            badge.className = 'keyword-pill secondary';
            badge.style.borderColor = 'rgba(139, 92, 246, 0.2)';
            badge.style.color = '#c084fc';
            badge.setAttribute('lang', 'hi'); // Support Devanagari font stack fallbacks
            badge.textContent = tag;
            DOM.modalTags.appendChild(badge);
        });
        DOM.modalTagsBlock.classList.remove('hidden');
    } else {
        DOM.modalTagsBlock.classList.add('hidden');
    }
    
    // Open Modal overlay
    DOM.detailModal.classList.remove('hidden');
    document.body.style.overflow = 'hidden'; // lock body scroll
}

function closeModal() {
    DOM.detailModal.classList.add('hidden');
    document.body.style.overflow = ''; // restore body scroll
}

// --- Setup Layout Architect View and Editorial Events ---
function setupArchitectEvents() {
    // Defensive null checks to prevent script crashes during caching transitions
    if (!DOM.navTabDashboard || !DOM.navTabArchitect || !DOM.dashboardView || !DOM.architectView) {
        console.warn("Layout Architect navigation tabs or view containers not found in the DOM. Browser caching may be active.");
        return;
    }
    
    // 1. View switching tab controls
    DOM.navTabDashboard.addEventListener('click', () => {
        DOM.navTabDashboard.classList.add('active');
        DOM.navTabArchitect.classList.remove('active');
        
        DOM.dashboardView.classList.remove('hidden');
        DOM.architectView.classList.add('hidden');
    });
    
    DOM.navTabArchitect.addEventListener('click', () => {
        DOM.navTabArchitect.classList.add('active');
        DOM.navTabDashboard.classList.remove('active');
        
        DOM.architectView.classList.remove('hidden');
        DOM.dashboardView.classList.add('hidden');
        
        // Re-populate the article list checklist
        renderArchitectChecklist();
    });
    
    // 2. Click listener on Persona cards grid
    const personaCards = document.querySelectorAll('.persona-card');
    personaCards.forEach(card => {
        card.addEventListener('click', () => {
            // Clear active classes
            personaCards.forEach(c => c.classList.remove('active'));
            // Set this one active
            card.classList.add('active');
            // Check the radio input inside it
            const radio = card.querySelector('input[name="persona-select"]');
            if (radio) radio.checked = true;
        });
    });
    
    // 3. Action button: Generate Editorial Newspaper Layout
    DOM.btnGenerateEditorial.addEventListener('click', () => {
        // Gather selected article IDs
        const checkedBoxes = DOM.architectChecklistContainer.querySelectorAll('.checklist-checkbox:checked');
        const articleIds = Array.from(checkedBoxes).map(box => parseInt(box.value));
        
        if (articleIds.length === 0) {
            alert("Please select at least one news article checklist story to design.");
            return;
        }
        
        const selectedPersonaRadio = document.querySelector('input[name="persona-select"]:checked');
        const personaValue = selectedPersonaRadio ? selectedPersonaRadio.value : "Standard";
        
        generateNewspaperLayout(articleIds, personaValue);
    });
    
    // 4. Action toolbar: Export HTML file
    DOM.btnDownloadHtml.addEventListener('click', () => {
        if (!generatedLayoutHtml) {
            alert("Please generate a newspaper layout sheet first before exporting.");
            return;
        }
        
        const blob = new Blob([generatedLayoutHtml], { type: 'text/html' });
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = 'newspaper_frontpage.html';
        link.click();
    });
    
    // 5. Action toolbar: Trigger print dialog
    DOM.btnPrintLayout.addEventListener('click', () => {
        if (!generatedLayoutHtml) {
            alert("Please generate a newspaper layout sheet first before printing.");
            return;
        }
        
        DOM.architectCanvas.contentWindow.focus();
        DOM.architectCanvas.contentWindow.print();
    });
}

// --- Render Article checklist in Architect sidebar ---
function renderArchitectChecklist() {
    DOM.architectChecklistContainer.innerHTML = '';
    
    if (articlesList.length === 0) {
        DOM.architectChecklistContainer.innerHTML = `
            <div style="text-align: center; padding: 2rem; color: var(--text-muted); font-size: 0.85rem;">
                No articles available in database.<br>Please upload a PDF file first.
            </div>
        `;
        return;
    }
    
    articlesList.forEach(article => {
        const item = document.createElement('div');
        item.className = 'checklist-item';
        
        item.innerHTML = `
            <input type="checkbox" class="checklist-checkbox" value="${article.article_id}">
            <div class="checklist-details">
                <h4 lang="hi">${article.headline}</h4>
                <div class="checklist-meta">
                    <span>Page ${article.page_number || '1'}</span>
                    <span>${article.dateline_or_author || 'Special Correspondent'}</span>
                </div>
            </div>
        `;
        
        // Clicking on the item anywhere toggles its checkbox
        item.addEventListener('click', (e) => {
            if (e.target.className !== 'checklist-checkbox') {
                const checkbox = item.querySelector('.checklist-checkbox');
                checkbox.checked = !checkbox.checked;
            }
        });
        
        DOM.architectChecklistContainer.appendChild(item);
    });
}

// --- API Call for Layout Generation ---
async function generateNewspaperLayout(articleIds, persona) {
    // 1. Show loading state overlay inside iframe wrapper
    const loader = document.createElement('div');
    loader.className = 'iframe-loader';
    loader.innerHTML = `
        <div style="text-align: center; padding: 2rem;">
            <h3 style="font-family: var(--font-heading); font-size: 1.5rem; margin-bottom: 12px;">Synthesizing Layout...</h3>
            <p style="color: var(--text-secondary); font-size: 0.9rem; margin-bottom: 2rem;">Gemini 3.1 Pro acting as Chief Editor editing columns and writing responsive HTML...</p>
            <div class="progress-bar-wrapper" style="width: 200px; margin: 0 auto;">
                <div class="progress-bar-fill" style="width: 100%; animation: pulse 1.5s infinite alternate;"></div>
            </div>
        </div>
    `;
    DOM.iframeWrapper.appendChild(loader);
    
    DOM.btnGenerateEditorial.disabled = true;
    DOM.btnGenerateEditorial.textContent = "Synthesizing Layout...";
    DOM.btnGenerateEditorial.style.opacity = "0.6";
    
    try {
        const response = await fetch('/api/generate-layout', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ article_ids: articleIds, persona: persona })
        });
        
        const result = await response.json();
        
        // Remove loader overlay
        loader.remove();
        DOM.btnGenerateEditorial.disabled = false;
        DOM.btnGenerateEditorial.textContent = "Generate Editorial Page";
        DOM.btnGenerateEditorial.style.opacity = "1";
        
        if (result.status === 'success') {
            generatedLayoutHtml = result.html;
            
            // Write HTML inside iframe Document
            const canvas = DOM.architectCanvas;
            const doc = canvas.contentDocument || canvas.contentWindow.document;
            doc.open();
            doc.write(result.html);
            doc.close();
        } else {
            alert(`Layout Generation Failed: ${result.detail || "API error occurred."}`);
            resetCanvasError();
        }
    } catch (error) {
        loader.remove();
        DOM.btnGenerateEditorial.disabled = false;
        DOM.btnGenerateEditorial.textContent = "Generate Editorial Page";
        DOM.btnGenerateEditorial.style.opacity = "1";
        
        console.error("Layout generation error:", error);
        alert("Failed to generate layout: Connection to the server failed.");
        resetCanvasError();
    }
}

function resetCanvasError() {
    generatedLayoutHtml = "";
    const canvas = DOM.architectCanvas;
    const doc = canvas.contentDocument || canvas.contentWindow.document;
    doc.open();
    doc.write(`
        <div style="color:#ef4444; text-align:center; padding: 6rem; font-family: sans-serif;">
            <h3>Editorial Synthesis Failed</h3>
            <p style="margin-top: 8px; color:#6b7280;">Failed to generate front-page layout. Please check server logs and retry.</p>
        </div>
    `);
    doc.close();
}
