package com.endless.liftlog.data.repository

import androidx.room.withTransaction
import com.endless.liftlog.data.db.LiftLogDatabase
import com.endless.liftlog.data.db.TemplateExercise
import com.endless.liftlog.data.db.TemplateExerciseDetail
import com.endless.liftlog.data.db.WorkoutTemplate
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.combine
import java.time.Instant

data class TemplateWithExercises(
    val template: WorkoutTemplate,
    val exercises: List<TemplateExerciseDetail>,
)

class TemplateRepository(private val db: LiftLogDatabase) {
    private val dao = db.templateDao()

    val templates: Flow<List<TemplateWithExercises>> =
        combine(dao.observeTemplates(), dao.observeAllTemplateExercises()) { templates, items ->
            val byTemplate = items.groupBy { it.templateId }
            templates.map { TemplateWithExercises(it, byTemplate[it.id].orEmpty()) }
        }

    suspend fun get(id: Long): TemplateWithExercises? {
        val template = dao.getTemplate(id) ?: return null
        return TemplateWithExercises(template, dao.getTemplateExercises(id))
    }

    /** Creates ([id] == null) or replaces a template with the given ordered exercise list. */
    suspend fun save(id: Long?, name: String, exerciseIds: List<Long>): Long = db.withTransaction {
        val templateId = if (id == null) {
            dao.insertTemplate(WorkoutTemplate(name = name.trim(), createdAt = Instant.now()))
        } else {
            val existing = requireNotNull(dao.getTemplate(id)) { "Template $id not found" }
            dao.updateTemplate(existing.copy(name = name.trim()))
            dao.clearTemplateExercises(id)
            id
        }
        dao.insertTemplateExercises(
            exerciseIds.mapIndexed { index, exerciseId ->
                TemplateExercise(templateId = templateId, exerciseId = exerciseId, position = index)
            },
        )
        templateId
    }

    suspend fun delete(id: Long) = dao.deleteTemplate(id)
}
