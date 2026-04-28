/* Lancet Research Platform - Shared JavaScript */

document.addEventListener('DOMContentLoaded', function() {

  /* ---- Mobile Nav Toggle ---- */
  const navToggle = document.querySelector('.nav-toggle');
  const navLinks = document.querySelector('.nav-links');
  if (navToggle && navLinks) {
    navToggle.addEventListener('click', function() {
      navLinks.classList.toggle('open');
    });
  }

  /* ---- Smooth Scroll ---- */
  document.querySelectorAll('a[href^="#"]').forEach(function(a) {
    a.addEventListener('click', function(e) {
      var href = a.getAttribute('href');
      if (href === '#') return;
      var target = document.querySelector(href);
      if (target) {
        e.preventDefault();
        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        if (navLinks) navLinks.classList.remove('open');
      }
    });
  });

  /* ---- Scroll Fade-In ---- */
  var fadeEls = document.querySelectorAll('.fade-up, .card, .price-card, .timeline-item');
  if ('IntersectionObserver' in window) {
    var obs = new IntersectionObserver(function(entries) {
      entries.forEach(function(entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('visible');
          entry.target.style.opacity = '1';
          entry.target.style.transform = 'translateY(0)';
          obs.unobserve(entry.target);
        }
      });
    }, { threshold: 0.08 });
    fadeEls.forEach(function(el) {
      if (!el.classList.contains('fade-up')) {
        el.style.opacity = '0';
        el.style.transform = 'translateY(24px)';
        el.style.transition = 'opacity 0.6s cubic-bezier(.16,1,.3,1), transform 0.6s cubic-bezier(.16,1,.3,1)';
      }
      obs.observe(el);
    });
  }

  /* ---- Back to Top Button ---- */
  var backBtn = document.querySelector('.back-to-top');
  if (backBtn) {
    window.addEventListener('scroll', function() {
      if (window.scrollY > 400) {
        backBtn.classList.add('visible');
      } else {
        backBtn.classList.remove('visible');
      }
    });
    backBtn.addEventListener('click', function() {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  }

  /* ---- OPC Floating Nav ---- */
  var floatingToggle = document.querySelector('.opc-floating-toggle');
  var floatingMenu = document.querySelector('.opc-floating-menu');
  if (floatingToggle && floatingMenu) {
    floatingToggle.addEventListener('click', function(e) {
      e.stopPropagation();
      floatingMenu.classList.toggle('open');
    });
    document.addEventListener('click', function(e) {
      if (!floatingMenu.contains(e.target) && e.target !== floatingToggle) {
        floatingMenu.classList.remove('open');
      }
    });
  }

  /* ---- Active Nav Link ---- */
  var currentPage = window.location.pathname.split('/').pop() || 'index.html';
  document.querySelectorAll('.nav-links a').forEach(function(link) {
    var href = link.getAttribute('href');
    if (href === currentPage || (currentPage === '' && href === 'index.html')) {
      link.classList.add('active');
    }
  });

});
