
    import * as THREE from 'three';
    import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
    import { VRMLoaderPlugin, VRMUtils } from '@pixiv/three-vrm';

    let currentVRM = null;
    let scene = null;
    let camera = null;
    let renderer = null;
    let clock = null;
    let targetExpression = 'idle';
    let currentExpression = 'idle';
    let expressionWeights = {};
    let isBlinking = false;
    let blinkTimer = 0;
    let nextBlinkInterval = 3.5;
    let isSpeaking = false;
    let isLoading = false;

    // Expose expression switcher to global window
    window.setCompanionExpression = function(exprName) {
        targetExpression = exprName.toLowerCase();
        currentExpression = targetExpression;
        isSpeaking = (targetExpression === 'speaking');
        if (!isSpeaking) {
            const mouthVisemes = ['aa', 'ih', 'ou', 'ee', 'oh'];
            mouthVisemes.forEach(v => applyBlendShape(v, 0.0));
        }


        // Update status indicator pill
        const pill = document.getElementById('companionStatusPill');
        if (pill) {
            pill.className = 'companion-status-pill ' + targetExpression;
            pill.textContent = '● ' + exprName.charAt(0).toUpperCase() + exprName.slice(1);
        }

    };

    window.stopCompanionSpeakingAnimation = function() {
        isSpeaking = false;
        const mouthVisemes = ['aa', 'ih', 'ou', 'ee', 'oh'];
        mouthVisemes.forEach(v => applyBlendShape(v, 0.0));
    };

    window.loadCompanionVRM = async function() {
        // Caching guard: If model is already loaded in memory, do not re-fetch 15.7MB asset!
        if (window.__companionVRMInstance) {
            currentVRM = window.__companionVRMInstance;
            const overlay = document.getElementById('companionLoadingOverlay');
            if (overlay) overlay.style.display = 'none';
            return;
        }

        if (isLoading) return;

        const container = document.getElementById('companionViewport');
        const canvas = document.getElementById('companionVrmCanvas');
        const overlay = document.getElementById('companionLoadingOverlay');
        const loadingText = document.getElementById('companionLoadingText');

        if (!container || !canvas) return;

        try {
            isLoading = true;
            if (overlay) overlay.style.display = 'flex';
            if (loadingText) loadingText.textContent = "Mounting 3D VRM Companion...";

            const width = (container.clientWidth && container.clientWidth > 0) ? container.clientWidth : 320;
            const height = (container.clientHeight && container.clientHeight > 0) ? container.clientHeight : 420;

            // 1. Scene
            scene = new THREE.Scene();

            // 2. Camera: Focused on Head & Upper Body with full head & hair headroom
            camera = new THREE.PerspectiveCamera(28.0, width / height, 0.1, 20.0);
            camera.position.set(0.0, 1.34, 1.05);
            camera.lookAt(new THREE.Vector3(0.0, 1.22, 0.0));

            // 3. WebGL Renderer
            renderer = new THREE.WebGLRenderer({ canvas: canvas, alpha: true, antialias: true });
            renderer.setSize(width, height);
            renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
            renderer.outputColorSpace = THREE.SRGBColorSpace;

            // 4. Lighting: Tailored studio lighting with metallic gold rim accents
            const ambientLight = new THREE.AmbientLight(0xfff7ed, 0.90);
            scene.add(ambientLight);

            // Warm Key light (front-right)
            const keyLight = new THREE.DirectionalLight(0xfff1d6, 1.35);
            keyLight.position.set(0.6, 1.8, 1.2);
            scene.add(keyLight);

            // Soft Fill light (front-left)
            const fillLight = new THREE.DirectionalLight(0xa5c5f8, 0.55);
            fillLight.position.set(-0.7, 1.4, 0.8);
            scene.add(fillLight);

            // Metallic Gold Rim light (back-center)
            const rimLight = new THREE.DirectionalLight(0xd4af37, 0.95);
            rimLight.position.set(0.0, 1.6, -1.0);
            scene.add(rimLight);

            clock = new THREE.Clock();

            // 5. GLTF + VRM Loader
            const loader = new GLTFLoader();
            loader.register((parser) => new VRMLoaderPlugin(parser));

            // URL resolution: Try local path, fallback to backend asset endpoint
            const localUrl = 'mira%20vrm.vrm';
            const apiBase = window.API_BASE || (typeof window.resolveApiBase === 'function' ? window.resolveApiBase() : (typeof resolveApiBase === 'function' ? resolveApiBase() : 'http://127.0.0.1:8000'));
            const serverUrl = `${apiBase}/api/ai/companion/model`;

            const fetchModel = (url) => {
                return new Promise((resolve, reject) => {
                    loader.load(
                        url,
                        (gltf) => resolve(gltf.userData.vrm),
                        (progress) => {
                            if (progress.total > 0 && loadingText) {
                                const pct = Math.round((progress.loaded / progress.total) * 100);
                                loadingText.textContent = `Loading 3D Model (${pct}%)...`;
                            }
                        },
                        (err) => reject(err)
                    );
                });
            };

            let vrm = null;
            try {
                vrm = await fetchModel(localUrl);
            } catch (localErr) {
                console.warn("Direct file load fallback to backend asset endpoint...", localErr);
                if (loadingText) loadingText.textContent = "Loading via CodeMind server...";
                vrm = await fetchModel(serverUrl);
            }

            if (!vrm) throw new Error("Could not instantiate VRM model");

            // Reset normalized rest pose to reference T-pose before posing
            if (vrm.humanoid && typeof vrm.humanoid.resetNormalizedPose === 'function') {
                vrm.humanoid.resetNormalizedPose();
            }

            // Preserve model integrity: Ensure frustum culling disabled and all bones maintain strictly unit scale (1, 1, 1)
            vrm.scene.traverse((obj) => {
                obj.frustumCulled = false;
                if (obj.isBone) {
                    obj.scale.set(1, 1, 1);
                }
            });

            // Rotate VRM 0.0 models if needed (VRMC 1.0 models maintain standard forward +Z)
            if (vrm.meta && (vrm.meta.metaVersion === '0' || vrm.meta.vrmVersion === '0.0')) {
                VRMUtils.rotateVRM0(vrm);
            }

            scene.add(vrm.scene);
            currentVRM = vrm;
            window.__companionVRMInstance = vrm;

            // Helper to apply natural relaxed upper-body idle pose with lowered arms (breaking T-pose)
            // Anatomically calibrated bone transforms:
            // - Upper arms lowered naturally along torso sides (-1.22 rad / +1.22 rad) with slight forward tilt
            // - Lower arms have pure elbow hinge flexion (+0.12 rad / -0.12 rad) with Z=0 and X=0 to eliminate skin twisting
            // - Hands in neutral rest alignment with forearms (0, 0, 0)
            // - Bone scales strictly clamped to unit (1, 1, 1), permanently eliminating stretched arms/hands
            function applyNaturalArmPose(humanoid, armBreathing = 0) {
                if (!humanoid) return;
                const lua = humanoid.getNormalizedBoneNode('leftUpperArm');
                if (lua) {
                    lua.rotation.set(0.08, -0.04, -1.22 + armBreathing);
                    lua.scale.set(1, 1, 1);
                }
                const lla = humanoid.getNormalizedBoneNode('leftLowerArm');
                if (lla) {
                    lla.rotation.set(0.0, 0.12, 0.0);
                    lla.scale.set(1, 1, 1);
                }
                const lh = humanoid.getNormalizedBoneNode('leftHand');
                if (lh) {
                    lh.rotation.set(0.0, 0.0, 0.0);
                    lh.scale.set(1, 1, 1);
                }

                const rua = humanoid.getNormalizedBoneNode('rightUpperArm');
                if (rua) {
                    rua.rotation.set(0.08, 0.04, 1.22 - armBreathing);
                    rua.scale.set(1, 1, 1);
                }
                const rla = humanoid.getNormalizedBoneNode('rightLowerArm');
                if (rla) {
                    rla.rotation.set(0.0, -0.12, 0.0);
                    rla.scale.set(1, 1, 1);
                }
                const rh = humanoid.getNormalizedBoneNode('rightHand');
                if (rh) {
                    rh.rotation.set(0.0, 0.0, 0.0);
                    rh.scale.set(1, 1, 1);
                }
            }


            try {
                applyNaturalArmPose(vrm.humanoid, 0);
            } catch (poseErr) {
                console.warn("Initial arm pose initialization notice:", poseErr);
            }

            // Frame camera with ample headroom and balanced upper body proportions
            try {
                const head = vrm.humanoid?.getNormalizedBoneNode('head');
                if (head) {
                    const headPos = new THREE.Vector3();
                    head.getWorldPosition(headPos);
                    camera.position.set(headPos.x, headPos.y + 0.01, headPos.z + 1.10);
                    camera.lookAt(new THREE.Vector3(headPos.x, headPos.y - 0.12, headPos.z));
                }
            } catch (e) {
                console.warn("Head framing alignment notice:", e);
            }

            // Fade out loading overlay
            if (overlay) {
                overlay.style.opacity = '0';
                setTimeout(() => { overlay.style.display = 'none'; }, 400);
            }

            // Window resize handler & dynamic container observer
            const handleResize = () => {
                if (!container || !renderer || !camera) return;
                const w = container.clientWidth;
                const h = container.clientHeight;
                if (w > 0 && h > 0) {
                    camera.aspect = w / h;
                    camera.updateProjectionMatrix();
                    renderer.setSize(w, h);
                }
            };
            window.addEventListener('resize', handleResize);
            if (window.ResizeObserver) {
                try {
                    const ro = new ResizeObserver(() => handleResize());
                    ro.observe(container);
                } catch (e) {
                    console.warn("ResizeObserver attachment notice:", e);
                }
            }

            // 6. Animation Render Loop
            const animate = () => {
                requestAnimationFrame(animate);

                // Throttling optimization when backgrounded or hidden (Req 34M)
                const viewport = document.getElementById('companionViewport');
                if (document.hidden || !viewport || viewport.offsetParent === null) {
                    return;
                }

                const delta = Math.min(clock.getDelta(), 0.04);
                const elapsed = clock.getElapsedTime();


                if (currentVRM) {
                    // Natural Idle Breathing (subtle sinusoidal rotation on chest and neck)
                    try {
                        const chest = currentVRM.humanoid?.getNormalizedBoneNode('chest') || currentVRM.humanoid?.getNormalizedBoneNode('spine');
                        if (chest) {
                            chest.rotation.x = Math.sin(elapsed * 1.6) * 0.018;
                        }
                        const neck = currentVRM.humanoid?.getNormalizedBoneNode('neck');
                        if (neck) {
                            neck.rotation.y = Math.sin(elapsed * 0.7) * 0.012;
                            neck.rotation.z = Math.cos(elapsed * 0.8) * 0.008;
                        }
                    } catch (e) {}

                    // Natural Relaxed Arm Pose with subtle breathing motion
                    try {
                        const armBreathing = Math.sin(elapsed * 1.6) * 0.010;
                        applyNaturalArmPose(currentVRM.humanoid, armBreathing);
                    } catch (e) {}

                    // Natural Eye Blinking Timer
                    blinkTimer += delta;
                    if (blinkTimer >= nextBlinkInterval) {
                        isBlinking = true;
                        if (blinkTimer >= nextBlinkInterval + 0.16) {
                            isBlinking = false;
                            blinkTimer = 0;
                            nextBlinkInterval = 3.0 + Math.random() * 2.5;
                        }
                    }
                    const blinkWeight = isBlinking ? (1.0 - Math.abs((blinkTimer - (nextBlinkInterval + 0.08)) / 0.08)) : 0.0;
                    applyBlendShape('blink', Math.max(0, Math.min(1, blinkWeight)));

                    // Speaking Mouth Lip Movement: synchronized multi-viseme cycling (Req 34H, 34I)
                    const mouthVisemes = ['aa', 'ih', 'ou', 'ee', 'oh'];
                    if (isSpeaking) {
                        const mouthOpen = Math.abs(Math.sin(elapsed * 9.0)) * 0.70;
                        const visemeIndex = Math.floor((elapsed * 4.5) % mouthVisemes.length);
                        mouthVisemes.forEach((v, idx) => {
                            applyBlendShape(v, idx === visemeIndex ? mouthOpen : 0.0);
                        });
                    } else {
                        mouthVisemes.forEach(v => applyBlendShape(v, 0.0));
                    }

                    // Expression Transitions
                    updateExpressions(delta, elapsed);

                    // Update VRM springs, physics, and expressions
                    currentVRM.update(delta);
                }

                renderer.render(scene, camera);
            };

            animate();
            isLoading = false;

        } catch (err) {
            console.error("3D VRM Companion failed to load:", err);
            isLoading = false;
            if (overlay) {
                overlay.innerHTML = `
                    <div style="font-size:32px; margin-bottom:8px;">⚠️</div>
                    <div style="color:#ef4444; font-weight:700; font-size:13px;">3D Model Unavailable</div>
                    <div style="color:#94a3b8; font-size:11px; max-width:280px; text-align:center; margin-top:4px;">
                        ${err.message || 'WebGL context error'}
                    </div>
                    <button onclick="window.loadCompanionVRM()" style="margin-top:12px; background:linear-gradient(135deg,#d4af37,#b8961e); border:none; color:#080808; font-weight:700; font-size:11px; padding:6px 14px; border-radius:6px; cursor:pointer;">Retry Load</button>
                `;
            }
        }
    };

    function applyBlendShape(name, value) {
        if (!currentVRM || !currentVRM.expressionManager) return;
        try {
            currentVRM.expressionManager.setValue(name, value);
        } catch (e) {}
    }

    function updateExpressions(delta, elapsed) {
        if (!currentVRM || !currentVRM.expressionManager) return;

        const targets = {
            happy: 0,
            relaxed: 0,
            surprised: 0,
            sad: 0,
            neutral: 0
        };

        switch (targetExpression) {
            case 'happy':
                targets.happy = 1.0;
                break;
            case 'encouraging':
                targets.happy = 0.55;
                targets.relaxed = 0.40;
                break;
            case 'listening':
                targets.relaxed = 0.35;
                targets.happy = 0.20;
                break;
            case 'thinking':
                targets.surprised = 0.20;
                targets.neutral = 0.40;
                break;
            case 'speaking':
                targets.happy = 0.30;
                targets.relaxed = 0.20;
                break;
            case 'confused':
                targets.sad = 0.35;
                targets.surprised = 0.35;
                break;
            case 'surprised':
                targets.surprised = 1.0;
                break;
            case 'idle':
            default:
                targets.relaxed = 0.25;
                break;
        }

        // Smooth Lerp transitions towards target weights
        for (const [expr, targetVal] of Object.entries(targets)) {
            const current = expressionWeights[expr] || 0.0;
            const next = current + (targetVal - current) * Math.min(1.0, delta * 5.0);
            expressionWeights[expr] = next;
            applyBlendShape(expr, next);
        }
    }

    // Auto-mount on load
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            setTimeout(window.loadCompanionVRM, 400);
        });
    } else {
        setTimeout(window.loadCompanionVRM, 400);
    }
    