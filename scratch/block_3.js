
    // Graceful offline/CDN fallback for Maya VRM companion
    window.loadCompanionVRM = window.loadCompanionVRM || function() {
        const overlay = document.getElementById('companionLoadingOverlay');
        if (overlay) {
            overlay.innerHTML = `
                <div style="font-size:28px; margin-bottom:6px;">🎭</div>
                <div style="color:#d4af37; font-weight:700; font-size:13px;">Maya AI Companion</div>
                <div style="color:#94a3b8; font-size:11px; max-width:240px; text-align:center; margin-top:4px;">
                    3D graphics offline. Conversational tutor, problem guidance, and step visualizers are active.
                </div>
            `;
            overlay.style.display = 'flex';
            overlay.style.opacity = '1';
        }
    };
    