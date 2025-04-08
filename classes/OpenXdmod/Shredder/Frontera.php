<?php

namespace OpenXdmod\Shredder;

use CCR\DB\iDatabase;
use CCR\Log;
use Configuration\XdmodConfiguration;
use OpenXdmod\Shredder\Slurm;
use PDODBMultiIngestor;
use Psr\Log\LoggerInterface;

class Frontera extends Slurm
{
    public function getJobIngestor($ingestAll = false)
    {
        $this->logger->debug('Creating ingestor');

        $sourceQuery = $this->getIngestorQuery($ingestAll);
        $insertFields = array_keys(static::$columnMap);
        $deleteStatement = $this->getIngestorDeleteStatement($ingestAll);

        $insertFields[] = 'source_format';

        $this->logger->debug("Ingestor source query: $sourceQuery");

        $this->logger->debug(
            'Ingestor insert fields: ' . implode(', ', $insertFields)
        );

        if ($deleteStatement != 'nodelete') {
            $this->logger->debug(
                "Ingestor delete statement: $deleteStatement"
            );
        } else {
            $this->logger->debug('No ingestor delete statement');
        }

        # This query is to manually apply gpu_counts to jobs submitted to the rtx / rtx-dev queues
        $updateGPUCounts = <<<SQL
UPDATE mod_shredder.shredded_job sj
SET
	sj.gpu_count = sj.node_count * 4
WHERE sj.queue_name IN ('rtx', 'rtx-dev') AND
      sj.shredded_job_id >  COALESCE((SELECT MAX(id) FROM mod_shredder.staging_job), 0)
SQL;

        $ingestor = new PDODBMultiIngestor(
            $this->db,
            $this->db,
            array(),
            $sourceQuery,
            'shredded_job',
            $insertFields,
            array($updateGPUCounts),
            $deleteStatement
        );

        $ingestor->setLogger($this->logger);

        return $ingestor;
    }

}
