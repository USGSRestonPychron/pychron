# ===============================================================================
# Copyright 2015 Jake Ross
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ===============================================================================

# ============= enthought library imports =======================
# ============= standard library imports ========================
from itertools import groupby
import time
import os
import json
# ============= local library imports  ==========================
from pychron.canvas.utils import make_geom
from pychron.database.isotope_database_manager import IsotopeDatabaseManager
from pychron.database.records.isotope_record import IsotopeRecordView
from pychron.dvc import jdump
from pychron.dvc.dvc import DVC
from pychron.dvc.dvc_persister import DVCPersister, format_experiment_identifier
from pychron.experiment.automated_run.persistence_spec import PersistenceSpec
from pychron.experiment.automated_run.spec import AutomatedRunSpec
from pychron.experiment.utilities.identifier import make_runid
from pychron.git_archive.repo_manager import GitRepoManager
from pychron.github import Organization
from pychron.loggable import Loggable
from pychron.paths import paths
from pychron.pychron_constants import ALPHAS

ORG = 'NMGRLData'


def create_github_repo(name):
    org = Organization(ORG)
    if not org.has_repo(name):
        usr = os.environ.get('GITHUB_USER')
        pwd = os.environ.get('GITHUB_PWD')
        org.create_repo(name, usr, pwd)


class IsoDBTransfer(Loggable):
    """
    transfer analyses from an isotope_db database to a dvc database
    """
    # meta_repo = Instance(MetaRepo)
    # root = None
    # repo_man = Instance(GitRepoManager)

    def _init_src_dest(self):
        conn = dict(host=os.environ.get('ARGONSERVER_HOST'),
                    username=os.environ.get('ARGONSERVER_DB_USER'),
                    password=os.environ.get('ARGONSERVER_DB_PWD'),
                    kind='mysql')

        self.dvc = DVC(bind=False, meta_repo_name='meta')
        self.dvc.db.trait_set(name='pychronmeta', **conn)
        if not self.dvc.initialize():
            self.warning_dialog('Failed to initialize DVC')
            return

        self.dvc.meta_repo.smart_pull(quiet=False)
        self.persister = DVCPersister(dvc=self.dvc)

        proc = IsotopeDatabaseManager(bind=False, connect=False)
        proc.db.trait_set(name='pychrondata', **conn)
        src = proc.db
        src.connect()
        self.processor = proc

    def runlist_load(self, path):
        with open(path, 'r') as rfile:
            runs = [li.strip() for li in rfile]
            # runs = [line.strip() for line in rfile if line.strip()]
            return filter(None, runs)

    def runlist_loads(self, txt):
        runs = [li.strip() for li in txt.striplines()]
        return filter(None, runs)

    def do_export(self, runs, experiment_id, creator, create_repo=False):

        self._init_src_dest()
        src = self.processor.db
        dest = self.dvc.db

        with src.session_ctx():
            key = lambda x: x.split('-')[0]
            runs = sorted(runs, key=key)
            with dest.session_ctx():
                repo = self._add_experiment(dest, experiment_id, creator, create_repo)

            self.persister.experiment_repo = repo
            self.dvc.experiment_repo = repo

            commit = False
            total = len(runs)
            j = 0

            for ln, ans in groupby(runs, key=key):
                with dest.session_ctx() as sess:
                    ans = list(ans)
                    n = len(ans)
                    for i, a in enumerate(ans):
                        st = time.time()
                        if self._transfer_analysis(a, experiment_id):
                            commit = True
                            print '{}/{} transfer time {:0.3f}'.format(j, total, time.time() - st)
                        j += 1

            if commit:
                repo.commit('<IMPORT> src= {}'.format(src.public_url))

    # private
    def _add_experiment(self, dest, experiment_id, creator, create_repo):
        experiment_id = format_experiment_identifier(experiment_id)

        # sys.exit()
        proot = os.path.join(paths.experiment_dataset_dir, experiment_id)
        if not os.path.isdir(proot):
            # create new local repo
            os.mkdir(proot)

            repo = GitRepoManager()
            repo.open_repo(proot)

            repo.add_ignore('.DS_Store')
            self.repo_man = repo
            if create_repo:
                # add repo to central location
                create_github_repo(experiment_id)

                url = 'https://github.com/{}/{}.git'.format(ORG, experiment_id)
                self.debug('Create repo at github. url={}'.format(url))
                repo.create_remote(url)
        else:
            repo = GitRepoManager()
            repo.open_repo(proot)

        dbexp = dest.get_experiment(experiment_id)
        if not dbexp:
            dest.add_experiment(experiment_id, creator)

        return repo

    def _transfer_meta(self, dest, dban):
        self.debug('transfer meta')

        dblab = dban.labnumber
        dbsam = dblab.sample
        project = dbsam.project.name
        project = project.replace('/', '_').replace('\\', '_')

        sam = dest.get_sample(dbsam.name, project)
        if not sam:
            mat = dbsam.material.name
            if not dest.get_material(mat):
                self.debug('add material {}'.format(mat))
                dest.add_material(mat)
                dest.flush()

            if not dest.get_project(project):
                self.debug('add project {}'.format(project))
                dest.add_project(project)
                dest.flush()

            self.debug('add sample {}'.format(dbsam.name))
            sam = dest.add_sample(dbsam.name, project, mat)
            dest.flush()

        dbirradpos = dblab.irradiation_position
        if not dbirradpos:
            irradname = 'NoIrradiation'
            levelname = 'A'
            holder = 'Grid'
            pos = None
            identifier = dblab.identifier
            doses = []
            prod = None
            prodname = 'NoIrradiation'

            geom = make_geom([(0, 0, 0.0175),
                              (1, 0, 0.0175),
                              (2, 0, 0.0175),
                              (3, 0, 0.0175),
                              (4, 0, 0.0175),

                              (0, 1, 0.0175),
                              (1, 1, 0.0175),
                              (2, 1, 0.0175),
                              (3, 1, 0.0175),
                              (4, 1, 0.0175),

                              (0, 2, 0.0175),
                              (1, 2, 0.0175),
                              (2, 2, 0.0175),
                              (3, 2, 0.0175),
                              (4, 2, 0.0175),

                              (0, 3, 0.0175),
                              (1, 3, 0.0175),
                              (2, 3, 0.0175),
                              (3, 3, 0.0175),
                              (4, 3, 0.0175),

                              (0, 4, 0.0175),
                              (1, 4, 0.0175),
                              (2, 4, 0.0175),
                              (3, 4, 0.0175),
                              (4, 4, 0.0175)
                              ])
        else:
            dblevel = dbirradpos.level
            dbirrad = dblevel.irradiation
            dbchron = dbirrad.chronology

            irradname = dbirrad.name
            levelname = dblevel.name
            holder = dblevel.holder.name
            prodname = dblevel.production.name
            pos = dbirradpos.position
            doses = dbchron.get_doses()
            prod = dblevel.production
            geom = dblevel.holder.geometry

        meta_repo = self.dvc.meta_repo
        # save db irradiation
        if not dest.get_irradiation(irradname):
            self.debug('Add irradiation {}'.format(irradname))
            dest.add_irradiation(irradname)
            dest.flush()

            meta_repo.add_irradiation(irradname)
            meta_repo.add_chronology(irradname, doses)
            meta_repo.commit('added irradiation {}'.format(irradname))

        # save production name to db
        if not dest.get_production(prodname):
            self.debug('Add production {}'.format(irradname))
            dest.add_production(prodname)
            dest.flush()

            meta_repo.add_production(prodname, prod)
            meta_repo.commit('added production {}'.format(prodname))

        # save db level
        if not dest.get_irradiation_level(irradname, levelname):
            self.debug('Add level irrad:{} level:{}'.format(irradname, levelname))
            dest.add_irradiation_level(levelname, irradname, holder, prodname)
            dest.flush()

            meta_repo.add_irradiation_holder(holder, geom)
            meta_repo.add_level(irradname, levelname)
            meta_repo.commit('added empty level {}{}'.format(irradname, levelname))

        if pos is None:
            pos = self._get_irradpos(dest, irradname, levelname, identifier)

        # save db irradiation position
        if not dest.get_irradiation_position(irradname, levelname, pos):
            self.debug('Add position irrad:{} level:{} pos:{}'.format(irradname, levelname, pos))
            p = meta_repo.get_level_path(irradname, levelname)
            with open(p, 'r') as rfile:
                yd = json.load(rfile)

            dd = dest.add_irradiation_position(irradname, levelname, pos)
            dd.identifier = dblab.identifier
            dd.sample = sam

            dest.flush()
            try:
                f = dban.labnumber.selected_flux_history.flux
                j, e = f.j, f.j_err
            except AttributeError:
                j, e = 0, 0

            yd.append({'j': j, 'j_err': e, 'position': pos, 'decay_constants': {}})
            jdump(yd, p)

    def _transfer_analysis(self, rec, exp, overwrite=True):
        dest = self.dvc.db
        proc = self.processor
        src = proc.db

        args = rec.split('-')
        idn = '-'.join(args[:-1])
        t = args[-1]
        try:
            aliquot = int(t)
            step = None
        except ValueError:
            aliquot = int(t[:-1])
            step = t[-1]

        if idn == '4359':
            idn = 'c-01-j'
        elif idn == '4358':
            idn = 'c-01-o'

        # check if analysis already exists. skip if it does
        if dest.get_analysis_runid(idn, aliquot, step):
            self.warning('{} already exists'.format(make_runid(idn, aliquot, step)))
            return

        dban = src.get_analysis_runid(idn, aliquot, step)
        iv = IsotopeRecordView()
        iv.uuid = dban.uuid

        self.debug('make analysis idn:{}, aliquot:{} step:{}'.format(idn, aliquot, step))
        an = proc.make_analysis(iv, unpack=True, use_cache=False)

        self._transfer_meta(dest, dban)

        dblab = dban.labnumber
        dbsam = dblab.sample

        if dblab.irradiation_position:
            irrad = dblab.irradiation_position.level.irradiation.name
            level = dblab.irradiation_position.level.name
            irradpos = dblab.irradiation_position.position
        else:
            irrad = 'NoIrradiation'
            level = 'A'
            irradpos = self._get_irradpos(dest, irrad, level, dblab.identifier)
            # irrad, level, irradpos = '', '', 0

        sample = dbsam.name
        mat = dbsam.material.name
        project = format_experiment_identifier(dbsam.project.name)
        extraction = dban.extraction
        ms = dban.measurement.mass_spectrometer.name
        if not dest.get_mass_spectrometer(ms):
            self.debug('adding mass spectrometer {}'.format(ms))
            dest.add_mass_spectrometer(ms)
            dest.flush()

        if step is None:
            inc = -1
        else:
            inc = ALPHAS.index(step)

        username = ''
        if dban.user:
            username = dban.user.name
            if not dest.get_user(username):
                self.debug('adding user. username:{}'.format(username))
                dest.add_user(username)
                dest.flush()

        rs = AutomatedRunSpec(labnumber=idn,
                              username=username,
                              material=mat,
                              project=project,
                              sample=sample,
                              irradiation=irrad,
                              irradiation_level=level,
                              irradiation_position=irradpos,
                              experiment_identifier=exp,
                              mass_spectrometer=ms,
                              uuid=dban.uuid,
                              _step=inc,
                              comment=dban.comment,
                              aliquot=int(aliquot),
                              extract_device=extraction.extraction_device.name,
                              duration=extraction.extract_duration,
                              cleanup=extraction.cleanup_duration,
                              beam_diameter=extraction.beam_diameter,
                              extract_units=extraction.extract_units or '',
                              extract_value=extraction.extract_value,
                              pattern=extraction.pattern or '',
                              weight=extraction.weight,
                              ramp_duration=extraction.ramp_duration or 0,
                              ramp_rate=extraction.ramp_rate or 0,

                              collection_version='0.1:0.1',
                              queue_conditionals_name='',
                              tray='')

        ps = PersistenceSpec(run_spec=rs,
                             tag=an.tag,
                             arar_age=an,
                             timestamp=dban.analysis_timestamp,
                             use_experiment_association=True,
                             positions=[p.position for p in extraction.positions])

        self.debug('transfer analysis with persister')
        self.persister.per_spec_save(ps, commit=False, msg_prefix='Database Transfer')
        return True

    def _get_irradpos(self, dest, irradname, levelname, identifier):
        dl = dest.get_irradiation_level(irradname, levelname)
        pos = 1
        if dl.positions:
            for p in dl.positions:
                if p.identifier == identifier:
                    pos = p.position
                    break
            else:
                pos = dl.positions[-1].position + 1

        return pos


def experiment_id_modifier(root, expid):
    for r, ds, fs in os.walk(root, topdown=True):
        fs = [f for f in fs if not f[0] == '.']
        ds[:] = [d for d in ds if not d[0] == '.']

        # print 'fff',r, os.path.basename(r)
        if os.path.basename(r) in ('intercepts', 'blanks', '.git',
                                   'baselines', 'icfactors', 'extraction', 'tags', '.data', 'monitor', 'peakcenter'):
            continue
        # dcnt+=1
        for fi in fs:
            # if not fi.endswith('.py') or fi == '__init__.py':
            #     continue
            # cnt+=1
            p = os.path.join(r, fi)
            # if os.path.basename(os.path.dirname(p)) =
            print p
            write = False
            with open(p, 'r') as rfile:
                jd = json.load(rfile)
                if 'experiment_identifier' in jd:
                    jd['experiment_identifier'] = expid
                    write = True

            if write:
                jdump(jd, p)


def load_path():
    path = '/Users/ross/Sandbox/dvc_imports/NM-276.txt'
    expid = 'Irradiation-NM-276'
    creator = 'mcintosh'

    runs = e.runlist_load(path)
    return runs, expid, creator


def load_import_request():
    import pymysql.cursors
    # Connect to the database
    connection = pymysql.connect(host='localhost',
                                 user=os.environ.get('DB_USER'),
                                 passwd=os.environ.get('DB_PWD'),
                                 db='labspy',
                                 cursorclass=pymysql.cursors.DictCursor)

    try:
        # connection is not autocommit by default. So you must commit to save
        # your changes.
        # connection.commit()

        with connection.cursor() as cursor:
            # Read a single record
            # sql = "SELECT `id`, `password` FROM `users` WHERE `email`=%s"
            # cursor.execute(sql, ('webmaster@python.org',))
            sql = '''SELECT * FROM importer_importrequest'''
            cursor.execute(sql)
            result = cursor.fetchone()

            runs = result['runlist_blob']
            expid = result['experiment_identifier']
            creator = result['requestor_name']

            return runs, expid, creator
    finally:
        connection.close()


if __name__ == '__main__':
    from pychron.core.helpers.logger_setup import logging_setup

    paths.build('_dev')
    logging_setup('de', root=os.path.join(os.path.expanduser('~'), 'Desktop', 'logs'))

    e = IsoDBTransfer()

    runs, expid, creator = load_path()
    runs, expid, creator = load_import_request()

    # e.do_export(runs, expid, creator, create_repo=False)

    # experiment_id_modifier('/Users/ross/Pychron_dev/data/.dvc/experiments/Irradiation-NM-274', 'Irradiation-NM-276')

    # create_github_repo('Irradiation-NM-272')
    # exp = 'J-Curve'
    # url = 'https://github.com/{}/{}.git'.format(org.name, exp)
    # # e.transfer_holder('40_no_spokes')
    # # e.transfer_holder('40_hole')
    # # e.transfer_holder('24_hole')
    #
    # path = '/Users/ross/Sandbox/dvc_imports/NM-275.txt'
    # expid = 'Irradiation-NM-275'
    # creator = 'mcintosh'
    # e.do_export(path, expid, creator, create_repo=False)

    # e.do_export_monitors(path, expid, creator, create_repo=False)
    # e.check_experiment(path, expid)
    # e.do_export(path, expid, creator, create_repo=False)
    # e.export_production('Triga PR 275', db=False)
    # ============= EOF =============================================
    # def _transfer_labnumber(self, ln, src, dest, exp=None, create_repo=False):
    # if exp is None:
    #     dbln = src.get_labnumber(ln)
    #     exp = dbln.sample.project.name
    #     # if exp in ('Chevron', 'J-Curve'):
    #     if exp in ('Chevron',):  # 'J-Curve'):
    #         return
    #

    # if not dest.get_experiment(exp):
    #     dest.add_experiment(name=exp)
    #     dest.flush()
    # if not dest.get_project(project):
    #     dest.add_project(project)

    # return self.repo_man

    # def _export_project(self, project, src, dest):
    #     proot = os.path.join(self.root, 'projects', project)
    #     # proot = os.path.join(paths.dvc_dir, 'projects', project)
    #     if not os.path.isdir(proot):
    #         os.mkdir(proot)
    #     repo = GitRepoManager()
    #     repo.open_repo(proot)
    #
    #     if not dest.get_project(project):
    #         dest.add_project(project)
    #
    #     return repo
    # def transfer_holder(self, name):
    #     self.root = os.path.join(os.path.expanduser('~'), 'Pychron_dev', 'data', '.dvc')
    #
    #     conn = dict(host='129.138.12.160', username='root', password='DBArgon', kind='mysql')
    #     # conn = dict(host='129.138.12.160', username='root', password='DBArgon', kind='mysql')
    #     # dest = DVCDatabase('/Users/ross/Sandbox/dvc/meta/testdb.sqlite')
    #     # dest = DVCDatabase(name='pychronmeta', **conn)
    #     # self.dvc = DVC(bind=False)
    #     # self.dvc.db.trait_set(name='pychronmeta', username='root',
    #     #                       password='Argon', kind='mysql', host='localhost')
    #
    #     self.meta_repo = MetaRepo()
    #     self.meta_repo.open_repo(os.path.join(self.root, 'meta'))
    #     proc = IsotopeDatabaseManager(bind=False, connect=False)
    #     proc.db.trait_set(name='pychrondata', **conn)
    #     src = proc.db
    #     # src = IsotopeAdapter(name='pychrondata', **conn)
    #     # src.trait_set()
    #     src.connect()
    #     with src.session_ctx():
    #         holder = src.get_irradiation_holder(name)
    #         self.meta_repo.add_irradiation_holder(name, holder.geometry)

    # def export_production(self, prodname, db=False):
    #     if db:
    #         pass
    #
    #     # self.root = os.path.join(os.path.expanduser('~'), 'Pychron_dev', 'data', '.dvc')
    #     self.meta_repo = MetaRepo(os.path.join(self.root, 'meta'))
    #
    #     conn = dict(host='129.138.12.160', username='root', password='DBArgon', kind='mysql')
    #     dest = DVCDatabase('/Users/ross/Sandbox/dvc/meta/testdb.sqlite')
    #     # dest = DVCDatabase(name='pychronmeta', **conn)
    #     dest.connect()
    #     src = IsotopeAdapter(name='pychrondata', **conn)
    #     # src.trait_set()
    #     src.connect()
    #     with src.session_ctx():
    #         if not dest.get_production(prodname):
    #             dest.add_production(prodname)
    #             dest.flush()
    #
    #             dbprod = src.get_irradiation_production(prodname)
    #             self.meta_repo.add_production(prodname, dbprod)
    #             self.meta_repo.commit('added production {}'.format(prodname))
    # def do_export_monitors(self, path, experiment_id, creator, create_repo=False):
    #     self.root = os.path.join(os.path.expanduser('~'), 'Pychron_dev', 'data', '.dvc')
    #     self.meta_repo = MetaRepo()
    #     self.meta_repo.open_repo(os.path.join(self.root, 'meta'))
    #
    #     conn = dict(host='129.138.12.160', username='root', password='DBArgon', kind='mysql')
    #     # conn = dict(host='129.138.12.160', username='root', password='DBArgon', kind='mysql')
    #     # dest = DVCDatabase('/Users/ross/Sandbox/dvc/meta/testdb.sqlite')
    #     # dest = DVCDatabase(name='pychronmeta', **conn)
    #     self.dvc = DVC(bind=False,
    #                    meta_repo_name='meta')
    #     self.dvc.db.trait_set(name='pychronmeta', username='root',
    #                           password='Argon', kind='mysql', host='localhost')
    #     if not self.dvc.initialize():
    #         self.warning_dialog('Failed to initialize DVC')
    #         return
    #
    #     self.persister = DVCPersister(dvc=self.dvc)
    #
    #     dest = self.dvc.db
    #
    #     proc = IsotopeDatabaseManager(bind=False, connect=False)
    #     proc.db.trait_set(name='pychrondata', **conn)
    #     src = proc.db
    #     # src = IsotopeAdapter(name='pychrondata', **conn)
    #     # src.trait_set()
    #     src.connect()
    #     with src.session_ctx():
    #         with open(path, 'r') as rfile:
    #             runs = [line.strip() for line in rfile if line.strip()]
    #
    #         key = lambda x: x.split('-')[0]
    #         runs = sorted(runs, key=key)
    #
    #         for r in runs:
    #             args = r.split('-')
    #             idn = '-'.join(args[:-1])
    #             t = args[-1]
    #             try:
    #                 aliquot = int(t)
    #                 step = None
    #             except ValueError:
    #                 aliquot = int(t[:-1])
    #                 step = t[-1]
    #             try:
    #                 int(idn)
    #             except:
    #                 continue
    #             dban = src.get_analysis_runid(idn, aliquot, step)
    #             if dban:
    #                 print idn, dban.labnumber.irradiation_position.level.irradiation.name
    #                 # runs = proc.make_analyses(runs)
    #                 # iv = IsotopeRecordView()
    #                 # iv.uuid = dban.uuid
    #                 # an = proc.make_analysis(iv, unpack=True, use_cache=False)
    #
    #                 # key = lambda x: x.irradiation
    #                 # runs = sorted(runs, key=key)
    #                 # for irrad, ais in groupby(runs, key=key):
    #                 #     print irrad, len(list(ais))
