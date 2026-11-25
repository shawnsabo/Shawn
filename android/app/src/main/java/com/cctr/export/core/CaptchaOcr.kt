package com.cctr.export.core

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import org.json.JSONArray
import java.nio.FloatBuffer
import kotlin.math.max

/**
 * 端侧离线图形验证码 OCR（与桌面端 ddddocr common_old.onnx 完全一致的推理与 CTC 解码）。
 */
class CaptchaOcr(context: Context) : AutoCloseable {
    private val env: OrtEnvironment = OrtEnvironment.getEnvironment()
    private val session: OrtSession
    private val charset: List<String>

    init {
        val modelBytes = context.assets.open("common_old.onnx").use { it.readBytes() }
        val opts = OrtSession.SessionOptions().apply {
            setIntraOpNumThreads(2)
        }
        try {
            session = env.createSession(modelBytes, opts)
        } finally {
            opts.close()
        }
        val charsetJson = context.assets.open("ddddocr_charset.json").bufferedReader().use { it.readText() }
        val arr = JSONArray(charsetJson)
        charset = List(arr.length()) { i -> arr.optString(i, "") }
    }

    fun recognize(imageBytes: ByteArray): String {
        val raw = BitmapFactory.decodeByteArray(imageBytes, 0, imageBytes.size) ?: return ""
        return try {
            val targetH = 64
            val targetW = max(1, (raw.width.toFloat() * (targetH.toFloat() / max(1, raw.height))).toInt())
            val resized = Bitmap.createScaledBitmap(raw, targetW, targetH, true)
            try {
                val pixels = IntArray(targetW * targetH)
                resized.getPixels(pixels, 0, targetW, 0, 0, targetW, targetH)
                val floats = FloatArray(targetW * targetH)
                for (i in pixels.indices) {
                    val p = pixels[i]
                    val r = (p shr 16) and 0xFF
                    val g = (p shr 8) and 0xFF
                    val b = p and 0xFF
                    // 标准亮度灰度归一化 [0, 1]（与 PIL convert('L') 一致）
                    val lum = (0.299f * r + 0.587f * g + 0.114f * b) / 255.0f
                    floats[i] = lum
                }

                val shape = longArrayOf(1L, 1L, targetH.toLong(), targetW.toLong())
                OnnxTensor.createTensor(env, FloatBuffer.wrap(floats), shape).use { inputTensor ->
                    val inputName = session.inputNames.first()
                    session.run(mapOf(inputName to inputTensor)).use { result ->
                        @Suppress("UNCHECKED_CAST")
                        val out = result[0].value as Array<Array<FloatArray>>
                        val sb = StringBuilder()
                        var prevIdx = -1
                        for (step in out.indices) {
                            val logits = out[step][0]
                            var bestIdx = 0
                            var bestVal = Float.NEGATIVE_INFINITY
                            for (c in logits.indices) {
                                if (logits[c] > bestVal) {
                                    bestVal = logits[c]
                                    bestIdx = c
                                }
                            }
                            if (bestIdx != prevIdx && bestIdx != 0 && bestIdx < charset.size) {
                                sb.append(charset[bestIdx])
                            }
                            prevIdx = bestIdx
                        }
                        sb.toString().replace(Regex("[^A-Za-z0-9]"), "")
                    }
                }
            } finally {
                if (resized !== raw) resized.recycle()
            }
        } finally {
            raw.recycle()
        }
    }

    override fun close() {
        session.close()
    }
}
