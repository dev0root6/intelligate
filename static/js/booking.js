// Dynamic passenger form generation for the Book Ticket page.

document.addEventListener('DOMContentLoaded', function() {
  const countSelect = document.getElementById('passengerCount');
  if (countSelect) {
    countSelect.addEventListener('change', function() {
      generatePassengerForms(parseInt(this.value, 10));
    });
    generatePassengerForms(parseInt(countSelect.value, 10));
  }

  const bookingForm = document.getElementById('bookingForm');
  if (bookingForm) {
    bookingForm.addEventListener('submit', function(e) {
      const count = parseInt(document.getElementById('passengerCount').value, 10);
      for (let i = 0; i < count; i++) {
        const faceInput = document.getElementById('p' + i + '_face');
        if (!faceInput || !faceInput.value) {
          e.preventDefault();
          alert('Please capture a face photo for passenger ' + (i + 1));
          return;
        }
      }
    });
  }
});

function generatePassengerForms(count) {
  const container = document.getElementById('passengerForms');
  container.innerHTML = '';

  for (let i = 0; i < count; i++) {
    const card = document.createElement('div');
    card.className = 'passenger-form-card fade-in';
    card.innerHTML =
      '<div class="pf-header">' +
        '<span class="pf-number">' + (i + 1) + '</span>' +
        '<h6 class="mb-0 fw-bold">Passenger ' + (i + 1) + '</h6>' +
      '</div>' +
      '<div class="row g-3">' +
        '<div class="col-md-4">' +
          '<label class="form-label">Name</label>' +
          '<input type="text" class="form-control" name="p' + i + '_name" required placeholder="Full name">' +
        '</div>' +
        '<div class="col-md-4">' +
          '<label class="form-label">Age</label>' +
          '<input type="number" class="form-control" name="p' + i + '_age" min="1" max="120" required placeholder="Age">' +
        '</div>' +
        '<div class="col-md-4">' +
          '<label class="form-label">Gender</label>' +
          '<select class="form-select" name="p' + i + '_gender" required>' +
            '<option value="">Select</option>' +
            '<option value="Male">Male</option>' +
            '<option value="Female">Female</option>' +
            '<option value="Other">Other</option>' +
          '</select>' +
        '</div>' +
      '</div>' +
      '<div class="row mt-3 align-items-center">' +
        '<div class="col-md-4 text-center">' +
          '<div class="capture-placeholder" id="p' + i + '_placeholder">' +
            '<i class="ph ph-camera" style="font-size:1.8rem;"></i>' +
            '<span>No photo yet</span>' +
          '</div>' +
          '<img class="face-preview" id="p' + i + '_preview">' +
          '<input type="hidden" name="p' + i + '_face" id="p' + i + '_face">' +
        '</div>' +
        '<div class="col-md-8 text-center">' +
          '<button type="button" class="btn-brand" onclick="captureFace(' + i + ')">' +
            '<i class="ph ph-camera"></i> Capture Face' +
          '</button>' +
        '</div>' +
      '</div>';
    container.appendChild(card);
  }
}

function captureFace(index) {
  openWebcam(function(dataUrl) {
    const preview = document.getElementById('p' + index + '_preview');
    const placeholder = document.getElementById('p' + index + '_placeholder');
    const hidden = document.getElementById('p' + index + '_face');
    preview.src = dataUrl;
    preview.classList.add('captured');
    placeholder.classList.add('hidden');
    hidden.value = dataUrl;
  });
}
