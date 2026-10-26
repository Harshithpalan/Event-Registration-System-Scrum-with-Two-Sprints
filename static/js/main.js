/**
 * EventHub - Client-side interactions & validation
 */

document.addEventListener('DOMContentLoaded', () => {
  initFlashDismissal();
  initFormValidation();
  initConfirmDialogs();
  initPrintTicket();
  initTableSearch();
});

/**
 * Automatically dismiss flash alerts after 5 seconds
 */
function initFlashDismissal() {
  const alerts = document.querySelectorAll('.alert');
  alerts.forEach(alert => {
    // Manual dismiss button
    const closeBtn = alert.querySelector('.alert-close');
    if (closeBtn) {
      closeBtn.addEventListener('click', () => {
        alert.style.opacity = '0';
        alert.style.transform = 'translateY(-10px)';
        setTimeout(() => alert.remove(), 250);
      });
    }

    // Auto dismiss after 6 seconds for non-danger alerts
    if (!alert.classList.contains('alert-danger')) {
      setTimeout(() => {
        if (document.body.contains(alert)) {
          alert.style.opacity = '0';
          alert.style.transform = 'translateY(-10px)';
          setTimeout(() => alert.remove(), 250);
        }
      }, 6000);
    }
  });
}

/**
 * Client-side validation for Event Registration form
 */
function initFormValidation() {
  const regForm = document.getElementById('registrationForm');
  if (!regForm) return;

  const nameInput = document.getElementById('attendeeName');
  const emailInput = document.getElementById('attendeeEmail');
  const submitBtn = document.getElementById('submitRegBtn');

  function validateEmail(email) {
    const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return re.test(String(email).toLowerCase());
  }

  function validateForm() {
    let isValid = true;

    if (nameInput) {
      if (nameInput.value.trim().length < 2) {
        nameInput.style.borderColor = 'var(--danger)';
        isValid = false;
      } else {
        nameInput.style.borderColor = 'var(--success)';
      }
    }

    if (emailInput) {
      if (!validateEmail(emailInput.value.trim())) {
        emailInput.style.borderColor = 'var(--danger)';
        isValid = false;
      } else {
        emailInput.style.borderColor = 'var(--success)';
      }
    }

    return isValid;
  }

  if (nameInput) nameInput.addEventListener('input', validateForm);
  if (emailInput) emailInput.addEventListener('input', validateForm);

  regForm.addEventListener('submit', (e) => {
    if (!validateForm()) {
      e.preventDefault();
      alert('Please fill out all required fields with valid information before submitting.');
    } else {
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = 'Securing Your Seat...';
      }
    }
  });
}

/**
 * Confirmation prompts for delete/cancel actions
 */
function initConfirmDialogs() {
  const deleteForms = document.querySelectorAll('form.confirm-action');
  deleteForms.forEach(form => {
    form.addEventListener('submit', (e) => {
      const msg = form.getAttribute('data-confirm') || 'Are you sure you want to perform this action?';
      if (!confirm(msg)) {
        e.preventDefault();
      }
    });
  });
}

/**
 * Print Ticket functionality on Confirmation Page
 */
function initPrintTicket() {
  const printBtn = document.getElementById('printTicketBtn');
  if (printBtn) {
    printBtn.addEventListener('click', () => {
      window.print();
    });
  }
}

/**
 * Filter data table rows in real-time
 */
function initTableSearch() {
  const searchInput = document.getElementById('tableSearchInput');
  if (!searchInput) return;

  const table = document.querySelector('.data-table');
  if (!table) return;

  searchInput.addEventListener('input', () => {
    const term = searchInput.value.toLowerCase().trim();
    const rows = table.querySelectorAll('tbody tr');

    rows.forEach(row => {
      const text = row.innerText.toLowerCase();
      if (text.includes(term)) {
        row.style.display = '';
      } else {
        row.style.display = 'none';
      }
    });
  });
}
