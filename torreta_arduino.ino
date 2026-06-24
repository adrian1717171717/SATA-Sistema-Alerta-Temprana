/*
 * ============================================================
 * S.A.V.I.A. V7.0 — FIRMWARE TORRETA CENTINELA (Arduino)
 * Recibe comandos "PAN,TILT\n" desde radar.py vía USB/Serial
 * y posiciona dos servos (Pan / Tilt) con control suavizado.
 *
 * Hardware requerido:
 *   - Arduino UNO / Nano / Mega
 *   - Servo Pan  → Pin 9
 *   - Servo Tilt → Pin 10
 *   - Fuente externa 5V para los servos (NO usar el 5V del Arduino)
 *   - GND común entre Arduino y fuente externa
 *
 * Subir con baudios = 9600
 * ============================================================
 */

#include <Servo.h>

// ── Configuración de pines ────────────────────────────────
const int PIN_PAN  = 9;
const int PIN_TILT = 10;

// ── Límites físicos de la montura ─────────────────────────
const int SERVO_MIN  = 0;
const int SERVO_MAX  = 180;
const int SERVO_IDLE = 90;   // Posición neutral (mirando al frente)

// ── Suavizado de movimiento (lerp) ────────────────────────
// Un valor de 0.0 = sin movimiento, 1.0 = salto directo
// 0.15 da un movimiento fluido sin vibración
const float ALPHA = 0.15f;

Servo servoPan;
Servo servoTilt;

float pan_actual  = SERVO_IDLE;
float tilt_actual = SERVO_IDLE;

int   pan_objetivo  = SERVO_IDLE;
int   tilt_objetivo = SERVO_IDLE;

String buffer_serial = "";

// ── Clamp: limita un valor entre [min, max] ───────────────
int clamp(int val, int lo, int hi) {
  if (val < lo) return lo;
  if (val > hi) return hi;
  return val;
}

// ── Setup ─────────────────────────────────────────────────
void setup() {
  Serial.begin(9600);

  servoPan.attach(PIN_PAN);
  servoTilt.attach(PIN_TILT);

  // Posición inicial neutral
  servoPan.write(SERVO_IDLE);
  servoTilt.write(SERVO_IDLE);

  Serial.println("S.A.V.I.A. TORRETA LISTA. Esperando comandos PAN,TILT...");
}

// ── Loop principal ─────────────────────────────────────────
void loop() {

  // ── 1. Leer serial ──────────────────────────────────────
  while (Serial.available() > 0) {
    char c = (char)Serial.read();

    if (c == '\n') {
      // Procesar el comando recibido
      buffer_serial.trim();
      int coma = buffer_serial.indexOf(',');

      if (coma != -1) {
        int pan_cmd  = buffer_serial.substring(0, coma).toInt();
        int tilt_cmd = buffer_serial.substring(coma + 1).toInt();

        pan_objetivo  = clamp(pan_cmd,  SERVO_MIN, SERVO_MAX);
        tilt_objetivo = clamp(tilt_cmd, SERVO_MIN, SERVO_MAX);
      }

      buffer_serial = "";   // Limpiar buffer para el próximo comando

    } else {
      buffer_serial += c;
    }
  }

  // ── 2. Suavizado de movimiento (interpolación lineal) ───
  // Mueve gradualmente la posición actual hacia el objetivo
  pan_actual  += ALPHA * (pan_objetivo  - pan_actual);
  tilt_actual += ALPHA * (tilt_objetivo - tilt_actual);

  // ── 3. Escribir en servos ─────────────────────────────
  servoPan.write((int)pan_actual);
  servoTilt.write((int)tilt_actual);

  // ── 4. Delay mínimo para no saturar el servo ──────────
  delay(15);   // ~66 Hz de actualización de servo
}
