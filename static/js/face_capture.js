// Face capture utility for the booking page webcam.
// Uses getUserMedia to stream the laptop webcam, captures a frame to canvas,
// and returns a base64 JPEG data URL.

let activeStream = null;
let activeTarget = null; // callback receiving the data URL

function openWebcam(targetCallback) {
  activeTarget = targetCallback;
  const modal = document.getElementById('webcamModal');
  const video = document.getElementById('webcamVideo');
  modal.classList.add('active');

  if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
    navigator.mediaDevices.getUserMedia({ video: { width: 480, height: 360 } })
      .then(function(stream) {
        activeStream = stream;
        video.srcObject = stream;
        video.play();
      })
      .catch(function(err) {
        alert('Unable to access webcam: ' + err.message);
        closeWebcam();
      });
  } else {
    alert('Webcam not supported by this browser.');
    closeWebcam();
  }
}

function captureFrame() {
  const video = document.getElementById('webcamVideo');
  const canvas = document.getElementById('webcamCanvas');
  const ctx = canvas.getContext('2d');

  canvas.width = 320;
  canvas.height = 320;
  // mirror to match preview
  ctx.save();
  ctx.scale(-1, 1);
  ctx.drawImage(video, -320, 0, 320, 320);
  ctx.restore();

  const dataUrl = canvas.toDataURL('image/jpeg', 0.85);
  if (activeTarget) activeTarget(dataUrl);
  closeWebcam();
}

function closeWebcam() {
  const modal = document.getElementById('webcamModal');
  const video = document.getElementById('webcamVideo');
  modal.classList.remove('active');
  if (activeStream) {
    activeStream.getTracks().forEach(function(t) { t.stop(); });
    activeStream = null;
  }
  if (video) video.srcObject = null;
  activeTarget = null;
}
