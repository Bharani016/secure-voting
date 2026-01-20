// static/animation.js

document.addEventListener("DOMContentLoaded", () => {
    
    const canvas = document.getElementById('bg-canvas');
    const ctx = canvas.getContext('2d');
    
    let width, height;
    let particles = [];
    
    // Configuration
    const particleCount = 250; // High density as requested
    const connectionDistance = 110; // Connect closer particles
    const mouseDistance = 200; // Mouse interaction radius

    let mouse = { x: null, y: null };

    // --- CURSOR SETUP ---
    const cursorDot = document.createElement('div');
    cursorDot.classList.add('cursor-dot');
    document.body.appendChild(cursorDot);

    window.addEventListener('mousemove', (e) => {
        mouse.x = e.x;
        mouse.y = e.y;
        
        // Move the custom cursor dot instantly
        cursorDot.style.left = e.x + 'px';
        cursorDot.style.top = e.y + 'px';
    });

    function resize() {
        width = canvas.width = window.innerWidth;
        height = canvas.height = window.innerHeight;
    }

    class Particle {
        constructor() {
            this.x = Math.random() * width;
            this.y = Math.random() * height;
            // Very slow, drifting movement (like water)
            this.vx = (Math.random() - 0.5) * 0.3; 
            this.vy = (Math.random() - 0.5) * 0.3;
            this.size = Math.random() * 2 + 0.5;
            
            // Colors: White and Transparent Cyan
            this.color = Math.random() > 0.5 ? 'rgba(255, 255, 255,' : 'rgba(0, 240, 255,';
            this.alpha = Math.random() * 0.5 + 0.1;
        }

        update() {
            this.x += this.vx;
            this.y += this.vy;

            // Bounce off edges
            if (this.x < 0 || this.x > width) this.vx *= -1;
            if (this.y < 0 || this.y > height) this.vy *= -1;

            // Gentle Mouse Interaction
            if (mouse.x != null) {
                let dx = mouse.x - this.x;
                let dy = mouse.y - this.y;
                let distance = Math.sqrt(dx * dx + dy * dy);
                
                if (distance < mouseDistance) {
                    const forceDirectionX = dx / distance;
                    const forceDirectionY = dy / distance;
                    const force = (mouseDistance - distance) / mouseDistance;
                    // Push particles away gently
                    const directionX = forceDirectionX * force * 1.5; 
                    const directionY = forceDirectionY * force * 1.5;

                    this.x -= directionX;
                    this.y -= directionY;
                }
            }
        }

        draw() {
            ctx.beginPath();
            ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
            ctx.fillStyle = this.color + this.alpha + ')';
            ctx.fill();
        }
    }

    function initParticles() {
        particles = [];
        for (let i = 0; i < particleCount; i++) {
            particles.push(new Particle());
        }
    }

    function animateParticles() {
        ctx.clearRect(0, 0, width, height);

        // Update and Draw Particles
        particles.forEach((p, index) => {
            p.update();
            p.draw();

            // Draw Connections (The "Web3 Net" effect)
            // Only connect to nearby particles to save performance & keep it clean
            for (let j = index + 1; j < particles.length; j++) {
                const p2 = particles[j];
                const dx = p.x - p2.x;
                const dy = p.y - p2.y;
                const dist = Math.sqrt(dx * dx + dy * dy);

                if (dist < connectionDistance) {
                    ctx.beginPath();
                    // Opacity fades as they get further apart
                    const opacity = 1 - (dist / connectionDistance);
                    ctx.strokeStyle = `rgba(99, 102, 241, ${opacity * 0.15})`; // Faint purple lines
                    ctx.lineWidth = 0.5;
                    ctx.moveTo(p.x, p.y);
                    ctx.lineTo(p2.x, p2.y);
                    ctx.stroke();
                }
            }
        });

        requestAnimationFrame(animateParticles);
    }

    // Initialize
    resize();
    initParticles();
    animateParticles();

    window.addEventListener('resize', () => {
        resize();
        initParticles();
    });
});


document.querySelectorAll("a").forEach(link => {
  if (link.href && link.target !== "_blank") {
    link.addEventListener("click", e => {
      e.preventDefault();
      document.body.classList.add("is-exiting");

      setTimeout(() => {
        window.location.href = link.href;
      }, 700);
    });
  }
});


  document.addEventListener("click", (e) => {
    const ripple = document.createElement("div");
    ripple.className = "cursor-ripple";
    ripple.style.left = `${e.clientX}px`;
    ripple.style.top = `${e.clientY}px`;

    document.body.appendChild(ripple);

    ripple.addEventListener("animationend", () => {
      ripple.remove();
    });
  });

  /* Mobile tap support */
  document.addEventListener("touchstart", (e) => {
    const touch = e.touches[0];
    if (!touch) return;

    const ripple = document.createElement("div");
    ripple.className = "cursor-ripple";
    ripple.style.left = `${touch.clientX}px`;
    ripple.style.top = `${touch.clientY}px`;

    document.body.appendChild(ripple);

    ripple.addEventListener("animationend", () => {
      ripple.remove();
    });
  });

