import sys
from time import sleep, time

import dask
from dask.distributed import Client
from distributed.utils_test import loop  # noqa: F401
import pytest

from dask_jobqueue import PBSCluster, MoabCluster

from . import QUEUE_WAIT


@pytest.mark.parametrize('Cluster', [PBSCluster, MoabCluster])
def test_header(Cluster):
    with Cluster(walltime='00:02:00', processes=4, threads=2, memory='7GB') as cluster:

        assert '#PBS' in cluster.job_header
        assert '#PBS -N dask_worker' in cluster.job_header
        assert '#PBS -l select=1:ncpus=8:mem=27GB' in cluster.job_header
        assert '#PBS -l walltime=00:02:00' in cluster.job_header
        assert '#PBS -q' not in cluster.job_header
        assert '#PBS -A' not in cluster.job_header

    with Cluster(queue='regular', project='DaskOnPBS', processes=4, threads=2, memory='7GB',
                 resource_spec='select=1:ncpus=24:mem=100GB') as cluster:

        assert '#PBS -q regular' in cluster.job_header
        assert '#PBS -N dask_worker' in cluster.job_header
        assert '#PBS -l select=1:ncpus=24:mem=100GB' in cluster.job_header
        assert '#PBS -l select=1:ncpus=8:mem=27GB' not in cluster.job_header
        assert '#PBS -l walltime=' in cluster.job_header
        assert '#PBS -A DaskOnPBS' in cluster.job_header

    with Cluster() as cluster:

        assert '#PBS -j oe' not in cluster.job_header
        assert '#PBS -N' in cluster.job_header
        assert '#PBS -l select=1:ncpus=' in cluster.job_header
        assert '#PBS -l walltime=' in cluster.job_header
        assert '#PBS -A' not in cluster.job_header
        assert '#PBS -q' not in cluster.job_header

    with Cluster(job_extra=['-j oe']) as cluster:

        assert '#PBS -j oe' in cluster.job_header
        assert '#PBS -N' in cluster.job_header
        assert '#PBS -l select=1:ncpus=' in cluster.job_header
        assert '#PBS -l walltime=' in cluster.job_header
        assert '#PBS -A' not in cluster.job_header
        assert '#PBS -q' not in cluster.job_header


@pytest.mark.parametrize('Cluster', [PBSCluster, MoabCluster])
def test_job_script(Cluster):
    with Cluster(walltime='00:02:00', processes=4, threads=2, memory='7GB') as cluster:

        job_script = cluster.job_script()
        assert '#PBS' in job_script
        assert '#PBS -N dask_worker' in job_script
        assert '#PBS -l select=1:ncpus=8:mem=27GB' in job_script
        assert '#PBS -l walltime=00:02:00' in job_script
        assert '#PBS -q' not in job_script
        assert '#PBS -A' not in job_script

        assert '{} -m distributed.cli.dask_worker tcp://'.format(sys.executable) in job_script
        assert '--nthreads 2 --nprocs 4 --memory-limit 7GB' in job_script

    with Cluster(queue='regular', project='DaskOnPBS', processes=4, threads=2, memory='7GB',
                 resource_spec='select=1:ncpus=24:mem=100GB') as cluster:

        job_script = cluster.job_script()
        assert '#PBS -q regular' in job_script
        assert '#PBS -N dask_worker' in job_script
        assert '#PBS -l select=1:ncpus=24:mem=100GB' in job_script
        assert '#PBS -l select=1:ncpus=8:mem=27GB' not in job_script
        assert '#PBS -l walltime=' in job_script
        assert '#PBS -A DaskOnPBS' in job_script

        assert '{} -m distributed.cli.dask_worker tcp://'.format(sys.executable) in job_script
        assert '--nthreads 2 --nprocs 4 --memory-limit 7GB' in job_script


@pytest.mark.env("pbs")  # noqa: F811
def test_basic(loop):
    with PBSCluster(walltime='00:02:00', processes=1, threads=2, memory='2GB',
                    local_directory='/tmp', job_extra=['-V'],
                    loop=loop) as cluster:
        with Client(cluster) as client:
            cluster.start_workers(2)
            assert cluster.pending_jobs or cluster.running_jobs
            future = client.submit(lambda x: x + 1, 10)
            assert future.result(QUEUE_WAIT) == 11
            assert cluster.running_jobs

            workers = list(client.scheduler_info()['workers'].values())
            w = workers[0]
            assert w['memory_limit'] == 2e9
            assert w['ncores'] == 2

            cluster.stop_workers(workers)

            start = time()
            while len(client.scheduler_info()['workers']) > 0:
                sleep(0.100)
                assert time() < start + QUEUE_WAIT

            assert not cluster.running_jobs


@pytest.mark.env("pbs")  # noqa: F811
def test_adaptive(loop):
    with PBSCluster(walltime='00:02:00', processes=1, threads=2, memory='2GB',
                    local_directory='/tmp', job_extra=['-V'],
                    loop=loop) as cluster:
        cluster.adapt()
        with Client(cluster) as client:
            future = client.submit(lambda x: x + 1, 10)
            assert cluster.pending_jobs or cluster.running_jobs
            assert future.result(QUEUE_WAIT) == 11

            start = time()
            while not len(cluster.pending_jobs):
                sleep(0.100)
                assert time() < start + QUEUE_WAIT

            start = time()
            while not len(cluster.running_jobs):
                sleep(0.100)
                assert time() < start + QUEUE_WAIT

            start = time()
            processes = cluster.worker_processes
            while len(client.scheduler_info()['workers']) != processes:
                sleep(0.1)
                assert time() < start + QUEUE_WAIT

            del future

            start = time()
            while len(client.scheduler_info()['workers']) > 0:
                sleep(0.100)
                assert time() < start + QUEUE_WAIT

            start = time()
            while cluster.pending_jobs or cluster.running_jobs:
                sleep(0.100)
                assert time() < start + QUEUE_WAIT


@pytest.mark.env("pbs")  # noqa: F811
def test_adaptive_grouped(loop):
    with PBSCluster(walltime='00:02:00', processes=2, threads=1, memory='2GB',
                    local_directory='/tmp', job_extra=['-V'],
                    loop=loop) as cluster:
        cluster.adapt(minimum=1)
        with Client(cluster) as client:
            future = client.submit(lambda x: x + 1, 10)
            assert future.result(QUEUE_WAIT) == 11

            start = time()
            while not len(cluster.pending_jobs):
                sleep(0.100)
                assert time() < start + QUEUE_WAIT

            start = time()
            while not len(cluster.running_jobs):
                sleep(0.100)
                assert time() < start + QUEUE_WAIT

            start = time()
            processes = cluster.worker_processes
            while len(client.scheduler_info()['workers']) != processes:
                sleep(0.1)
                assert time() < start + QUEUE_WAIT

            del future

            start = time()
            while len(client.scheduler_info()['workers']) > 0:
                sleep(0.100)
                assert time() < start + QUEUE_WAIT

            start = time()
            while cluster.pending_jobs or cluster.running_jobs:
                sleep(0.100)
                assert time() < start + QUEUE_WAIT


def test_valid_worker_name():
    with pytest.raises(ValueError):
        PBSCluster(name='dask-worker')


def test_config(loop):  # noqa: F811
    with dask.config.set({'jobqueue.pbs.walltime': '00:02:00',
                          'jobqueue.pbs.local-directory': '/foo'}):
        with PBSCluster(loop=loop) as cluster:
            assert '00:02:00' in cluster.job_script()
            assert '--local-directory /foo' in cluster.job_script()
