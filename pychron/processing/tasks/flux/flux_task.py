#===============================================================================
# Copyright 2013 Jake Ross
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#===============================================================================

#============= enthought library imports =======================
from collections import namedtuple
import struct
from traits.api import on_trait_change
from traitsui.tabular_adapter import TabularAdapter
from pyface.tasks.task_layout import TaskLayout, HSplitter, VSplitter, PaneItem, Tabbed
#============= standard library imports ========================
from numpy import asarray, average
#============= local library imports  ==========================
from uncertainties import ufloat
from pychron.database.records.isotope_record import IsotopeRecordView
from pychron.processing.analyses.analysis import Analysis
from pychron.processing.tasks.flux.flux_parser import XLSFluxParser, CSVFluxParser
from pychron.processing.tasks.flux.panes import IrradiationPane
from pychron.processing.tasks.analysis_edit.interpolation_task import InterpolationTask
from pychron.processing.tasks.analysis_edit.panes import TablePane
from pychron.processing.argon_calculations import calculate_flux

Position = namedtuple('Positon', 'position x y')


class LevelAdapter(TabularAdapter):
    columns = [('Run ID', 'identifier'), ('Pos.', ('position'))]
    #identifier_text = Property
    font = 'helvetica 10'

    #def _get_identifier_text(self):
    #print self.item
    #return self.item
    #return self.item.labnumber.identifier


class UnknownsAdapter(LevelAdapter):
    pass


class ReferencesAdapter(LevelAdapter):
    pass


class UnknownsPane(TablePane):
    id = 'pychron.analysis_edit.unknowns'
    name = 'Unknowns'


class ReferencesPane(TablePane):
    name = 'References'
    id = 'pychron.analysis_edit.references'


class FluxTask(InterpolationTask):
    name = 'Flux'
    id = 'pychron.analysis_edit.flux'
    flux_editor_count = 1
    unknowns_adapter = UnknownsAdapter
    references_adapter = ReferencesAdapter
    references_pane_klass = ReferencesPane
    unknowns_pane_klass = UnknownsPane

    def find_associated_analyses(self):
        pass

    def _default_layout_default(self):
        return TaskLayout(
            id='pychron.analysis_edit',
            left=HSplitter(
                VSplitter(
                    PaneItem('pychron.analysis_edit.irradiation'),
                    Tabbed(
                        PaneItem('pychron.analysis_edit.unknowns'),
                        PaneItem('pychron.analysis_edit.references')),
                    PaneItem('pychron.analysis_edit.controls'))
            ),
        )

    def create_dock_panes(self):
        panes = super(FluxTask, self).create_dock_panes()
        return panes + [
            IrradiationPane(model=self.manager)]

    def new_flux(self):
        from pychron.processing.tasks.flux.flux_editor import FluxEditor

        editor = FluxEditor(name='Flux {:03n}'.format(self.flux_editor_count),
                            processor=self.manager)

        self._open_editor(editor)
        self.flux_editor_count += 1


    @on_trait_change('manager:level')
    def _level_changed(self, new):
        if new:
            with self.manager.db.session_ctx():
                level = self.manager.get_level(new)
                if self.active_editor:
                    self.active_editor.level = level

                if level:
                    refs, unks = self.manager.group_level(level)
                    r, u = list(refs), list(unks)
                    self.unknowns_pane.items = u
                    self.references_pane.items = r

                    # self.active_editor.set_items(u)
                    # self.active_editor.references= r

    @on_trait_change('active_editor:tool:calculate_button')
    def _calculate_flux(self):
        if self.references_pane.items:
            editor = self.active_editor
            editor.monitor_positions = {}
            editor.positions_dirty=True
            editor.suppress_update=True
            db=self.manager.db
            with db.session_ctx():
                geom = self._get_geometry()
                editor.geometry = geom
                def add_pos(i, use=False):
                    ref = db.get_labnumber(i.identifier)
                    pid = ref.irradiation_position.position
                    ident = ref.identifier
                    sample=''
                    if ref.sample:
                        sample=ref.sample.name

                    cj = ref.selected_flux_history.flux.j
                    cjerr = ref.selected_flux_history.flux.j_err
                    x, y, r = geom[pid - 1]

                    editor.add_position(int(pid), ident, sample, x, y, cj, cjerr, use)

                for ii in self.unknowns_pane.items:
                    add_pos(ii, use=False)

                for ii in self.references_pane.items:
                    add_pos(ii, use=True)

                editor.positions_dirty=True

                if editor.tool.data_source == 'database':
                    self._calculate_flux_db(editor)
                else:
                    self._calculate_flux_file(editor)

                editor.rebuild_graph()
                editor.set_unknown_j()
                editor.suppress_update = False

    def _calculate_flux_file(self, editor):
        #p = self.open_file_dialog()
        p = '/Users/ross/Sandbox/flux_visualizer/Tray I NM-261.xls'
        if p:
            #open flux file parser
            if p.endswith('.xls'):
                parser = XLSFluxParser(path=p)
            else:
                parser = CSVFluxParser(path=p)

            irrad, level = parser.get_irradiation()
            geom = self._get_geometry(irrad=irrad, level=level)
            editor.geometry = geom

            n = parser.get_npositions()
            prog = self.manager.open_progress(n=n)

            for pos in parser.iterpositions():

                pid = pos.hole_id

                prog.change_message('Loading Position {}'.format(pid))

                #get x,y from geometry
                try:
                    x, y, r = geom[pid - 1]
                    editor.add_monitor_position(pid, pos.identifier, x, y, pos.j, pos.je)
                except IndexError:
                    self.warning('Skipping hole {}. Only {} in this tray'.format(pid, len(geom)))
            prog.close()

    def _calculate_flux_db(self, editor):

        monitor_age = editor.tool.monitor_age

        # helper funcs
        def calc_j(ai):
            ar40=ai.get_interference_corrected_value('Ar40')
            ar39=ai.get_interference_corrected_value('Ar39')

            # ar40 = ai.isotopes['Ar40'].get_interference_corrected_value()
            # ar39 = ai.isotopes['Ar39'].get_interference_corrected_value()
            return calculate_flux(ar40, ar39, monitor_age)

        def mean_j(ans):
            js, errs = zip(*[calc_j(ai) for ai in ans])
            errs = asarray(errs)
            wts = errs ** -2
            m, ss = average(js, weights=wts, returned=True)
            return ufloat(m, ss ** -0.5)

        proc = self.manager
        db = proc.db
        with db.session_ctx():
            refs = self.references_pane.items
            ans, tcs = zip(*[db.get_labnumber_analyses(ri.identifier) for ri in refs])
            #print ans
            #print tcs
            prog = proc.open_progress(n=sum(tcs), close_at_end=False)

            geom = self._get_geometry()
            editor = self.active_editor
            editor.geometry = geom

            for ais in ans:
                if ais:
                    ref = ais[0]
                    pid = ref.labnumber.irradiation_position.position
                    ident = ref.labnumber.identifier
                    cj=ref.labnumber.selected_flux_history.flux.j
                    x, y, r = geom[pid - 1]
                    aa = proc.make_analyses(ais, progress=prog)
                    j = mean_j(aa)

                    dev=100
                    if cj:
                        dev=(j.nominal_value-cj)/cj*100

                    editor.set_position_j(ident, j.nominal_value, j.std_dev, dev)
                    # editor.add_monitor_position(int(pid), ident, x, y, j.nominal_value, j.std_dev, dev)

            prog.close()

    def _get_geometry(self, irrad=None, level=None, holder=None):
        man = self.manager

        db = man.db
        with db.session_ctx():
            if holder is None:
                if irrad is None:
                    irrad = man.irradiation
                    level = man.level

                level = db.get_irradiation_level(irrad, level)
                holder = level.holder
            else:
                holder = db.get_irradiation_holder(holder)

            geom = holder.geometry
            return [struct.unpack('>fff', geom[i:i + 12])
                    for i in xrange(0, len(geom), 12)]

    @on_trait_change('unknowns_pane:[items, update_needed, dclicked, refresh_editor_needed]')
    def _update_unknowns_runs(self, obj, name, old, new):
        if name == 'dclicked':
            if new:
                if isinstance(new.item, (IsotopeRecordView, Analysis)):
                    self._recall_item(new.item)
        elif name == 'refresh_editor_needed':
            self.active_editor.rebuild()
        # else:
        #     if not obj._no_update:
        #         if self.active_editor:
        #             self.active_editor.set_items(self.unknowns_pane.items)
        #         if self.plot_editor_pane:
        #             self.plot_editor_pane.analyses = self.unknowns_pane.items

    def _active_editor_changed(self):
        if self.active_editor:
            if self.controls_pane:
                tool = None
                if hasattr(self.active_editor, 'tool'):
                    tool = self.active_editor.tool

                self.controls_pane.tool = tool

            # if self.unknowns_pane:
            #     # if hasattr(self.unknowns_pane, 'previous_selections'):
            #     #     self.unknowns_pane.previous_selection = self.unknowns_pane.previous_selections[0]
            #     if hasattr(self.active_editor, 'analyses'):
            #         #if self.active_editor.unknowns:
            #         self.unknowns_pane.items = self.active_editor.analyses
#============= EOF =============================================
