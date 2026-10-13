
    (function() {
        'use strict';
        var canvas = document.getElementById('goldCanvas');
        if (!canvas) return;
        var ctx = canvas.getContext('2d');

        // Resize canvas to fill viewport
        function resize() {
            canvas.width  = window.innerWidth;
            canvas.height = window.innerHeight;
        }
        resize();
        window.addEventListener('resize', resize);

        // Metallic gold palette (no yellows/neons — proper gold tones)
        var GOLD_COLORS = [
            'rgba(247,231,122,',  // specular highlight
            'rgba(212,175,55,',   // champagne gold
            'rgba(184,150,30,',   // warm bronze-gold
            'rgba(200,160,25,',   // mid gold
            'rgba(230,190,60,',   // light gold
            'rgba(160,120,18,',   // deep gold
        ];

        function randomGoldColor(alpha) {
            return GOLD_COLORS[Math.floor(Math.random() * GOLD_COLORS.length)] + alpha + ')';
        }

        // Particle factory
        function createParticle() {
            var x     = Math.random() * canvas.width;
            var y     = canvas.height + Math.random() * 80;
            var size  = 0.4 + Math.random() * 1.8;       // 0.4–2.2 px
            var speed = 0.18 + Math.random() * 0.32;      // very slow rise
            var drift = (Math.random() - 0.5) * 0.25;    // subtle horizontal sway
            var alpha = 0.06 + Math.random() * 0.32;      // keep dim & realistic
            var pulse = Math.random() * Math.PI * 2;      // phase offset
            var color = randomGoldColor(alpha.toFixed(3));
            return { x: x, y: y, size: size, speed: speed, drift: drift,
                     alpha: alpha, pulse: pulse, color: color };
        }

        // Initialise ~90 particles
        var PARTICLE_COUNT = 90;
        var particles = [];
        for (var i = 0; i < PARTICLE_COUNT; i++) {
            var p = createParticle();
            p.y = Math.random() * canvas.height; // scatter initial y
            particles.push(p);
        }

        var frame = 0;
        function draw() {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            frame++;

            for (var i = 0; i < particles.length; i++) {
                var p = particles[i];
                // Gentle breathing pulse (±15% alpha)
                var pAlpha = p.alpha * (0.85 + 0.15 * Math.sin(frame * 0.018 + p.pulse));

                // Draw particle as soft glowing dot
                ctx.beginPath();
                ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);

                var grad = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.size * 2.5);
                grad.addColorStop(0,   randomGoldColor(pAlpha.toFixed(3)));
                grad.addColorStop(0.5, randomGoldColor((pAlpha * 0.5).toFixed(3)));
                grad.addColorStop(1,   'rgba(0,0,0,0)');
                ctx.fillStyle = grad;
                ctx.fill();

                // Rise & drift
                p.y    -= p.speed;
                p.x    += p.drift + Math.sin(frame * 0.012 + p.pulse) * 0.12;

                // Recycle when particle drifts off top
                if (p.y < -10) {
                    particles[i] = createParticle();
                }
            }

            requestAnimationFrame(draw);
        }

        draw();
    })();
    