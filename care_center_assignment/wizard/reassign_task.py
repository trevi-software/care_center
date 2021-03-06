# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ReassignTaskWizard(models.TransientModel):
    _name = 'reassign_task.wizard'
    _description = 'Reassign Task to User or Team'


    task_id = fields.Many2one('project.task', string='Task')
    name = fields.Char('Summary', required=True,
                       help='Short explanation for reassigning the Task.')
    description = fields.Html('Description', required=False,
                              help='Extended explanation for reassigning the Task.')
    reassign_to = fields.Selection([
        ('user', 'User'),
        ('team', 'Team'),
        ('myself', 'Myself')
    ],
     'Reassign To', required=True, default='user')
    assigned_to = fields.Many2one('res.users', string='Assigned To',
                                  index=True, ondelete='set null')
    team_id = fields.Many2one('crm.team', string='Team', index=True,
                              ondelete='set null',
                              help='New Team responsible for performing this Task')
    reassign_subtasks = fields.Boolean('Reassign Subtasks', default=True)

    @api.constrains('assigned_to', 'team_id')
    def verify_assignment_changed(self):
        if self.assigned_to:
            if self.assigned_to.id == self.task_id.user_id.id:
                raise ValidationError(
                    'The Task is already assigned to %s' % self.assigned_to.name
                )

        if self.team_id:
            if self.team_id == self.task_id.team_id:
                raise ValidationError(
                    'The Task is already assigned to the %s Team' % self.team_id.name
                )

    @api.onchange('reassign_to')
    def reset_assignment(self):
        self.team_id = None
        self_assigned = 'Self-assign Task'

        if self.reassign_to == 'myself':
            self.assigned_to = self.env.uid
            if not self.name:
                self.name = self_assigned
        else:
            self.assigned_to = None
            if self.name == self_assigned:
                self.name = None

    def assignment(self):
        if self.team_id:
            return u'the %s Team' % self.team_id.name
        return u'you'

    def get_partner_ids(self):
        if self.assigned_to:
            return [self.assigned_to.partner_id.id]

        member_ids = self.team_id.member_ids.mapped('partner_id.id')
        if self.team_id.user_id:
            member_ids.append(self.team_id.user_id.partner_id.id)
        return member_ids

    def get_subject(self):
        if self.assigned_to:
            return u'%s has assigned a Task to you' % self.env.user.name
        return u'{by} has assigned a Task to the {team} Team'.format(
            by=self.env.user.name,
            team=self.team_id.name,
        )

    def get_body(self,):
        return u"""
        <p>{by} has assigned the <b>{task}</b> Task to {assignment} </p>
        <p><b>Summary: </b>{summary}</p>
        <p><b>Description: </b></p>
        {description} 
        """.format(
            by=self.env.user.name,
            assignment=self.assignment(),
            summary=self.name,
            task=self.task_id.name,
            description=self.description,
        )

    @api.multi
    def reassign_user_team(self):

        assignment = self.env['task.assignment'].create({
            'name': self.name,
            'description': self.description,
            'assigned_by': self.env.uid,
            'assigned_to': self.assigned_to and self.assigned_to.id,
            'team_id': self.team_id and self.team_id.id,
            'task_id': self.task_id.id,
        })

        stats = {}
        if self.assigned_to:
            stats['user_id'] = self.assigned_to.id
        if self.team_id:
            stats['team_id'] = self.team_id.id
            stats['user_id'] = self.team_id.user_id and self.team_id.user_id.id

        if self.reassign_subtasks:
            for subtask in self.task_id.child_task_ids:
                subtask.with_context({'tracking_disable': True}).write(stats)

        stats['assignment_ids'] = [(4, assignment.id, None)]
        self.task_id.with_context({'tracking_disable': True}).write(stats)

        self.task_id.message_post(
            body=self.get_body(),
            subject=self.get_subject(),
            message_type='email',
            subtype=None,
            parent_id=False,
            attachments=None,
            content_subtype='html',
            partner_ids=self.get_partner_ids(),
        )

        return True
