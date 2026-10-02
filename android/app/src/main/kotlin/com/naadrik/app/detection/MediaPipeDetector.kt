package com.naadrik.app.detection

import android.content.Context
import android.graphics.Bitmap
import com.google.mediapipe.framework.image.BitmapImageBuilder
import com.google.mediapipe.tasks.core.BaseOptions
import com.google.mediapipe.tasks.core.Delegate
import com.google.mediapipe.tasks.vision.core.RunningMode
import com.google.mediapipe.tasks.vision.objectdetector.ObjectDetector
import com.naadrik.core.config.Config
import com.naadrik.core.perception.Box
import com.naadrik.core.perception.Detection

/** MediaPipe Tasks object detector (EfficientDet-Lite0, COCO), the same model family as desktop. */
class MediaPipeDetector(
    context: Context,
    config: Config,
) : AutoCloseable {
    private val detector: ObjectDetector =
        ObjectDetector.createFromOptions(
            context,
            ObjectDetector.ObjectDetectorOptions
                .builder()
                .setBaseOptions(
                    BaseOptions
                        .builder()
                        .setModelAssetPath(config.android.detectionModel)
                        .setDelegate(if (config.android.detectionDelegate == "gpu") Delegate.GPU else Delegate.CPU)
                        .build(),
                ).setRunningMode(RunningMode.IMAGE)
                .setMaxResults(config.detection.maxResults)
                .setScoreThreshold(config.detection.scoreThreshold.toFloat())
                .build(),
        )

    fun detect(bitmap: Bitmap): List<Detection> {
        val result = detector.detect(BitmapImageBuilder(bitmap).build())
        val w = bitmap.width.toDouble()
        val h = bitmap.height.toDouble()
        return result.detections().map { detection ->
            val category = detection.categories().first()
            val box = detection.boundingBox()
            Detection(
                Box(box.left / w, box.top / h, box.right / w, box.bottom / h),
                category.categoryName().ifEmpty { "object" },
                category.score().toDouble(),
            )
        }
    }

    override fun close() = detector.close()
}
