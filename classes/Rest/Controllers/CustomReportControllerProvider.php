<?php

namespace Rest\Controllers;

use CCR\DB;
use CCR\Log;
use Exception;
use Psr\Log\LoggerInterface;
use Silex\Application;
use Silex\ControllerCollection;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\HttpKernel\Exception\NotFoundHttpException;

class CustomReportControllerProvider extends BaseControllerProvider
{
    const LOG_MODULE = 'custom-report-controller';

    /**
     * @var LoggerInterface
     */
    private $logger;

    public function __construct(array $params = [])
    {
        parent::__construct($params);
        $this->logger = Log::factory(
            self::LOG_MODULE,
            [
                'console' => false,
                'file' => false,
                'mail' => false
            ]
        );
    }

    /**
     * Set up data warehouse export routes.
     *
     * @param Application $app
     * @param ControllerCollection $controller
     */
    public function setupRoutes(
        Application $app,
        ControllerCollection $controller
    ) {
        $root = $this->prefix;
        $current = get_class($this);

        $controller->get("$root/reports", "$current::getReports");

        $controller->get("$root/thumbnail/{report_id}", "$current::getReportThumbnail")
            ->assert('report_id', '(\w|_|-])+');

        $controller->get("$root/report/{report_id}", "$current::getReport")
            ->assert('report_id', '(\w|_|-])+');

        $controller->get("$root/report-directory", "$current::getReportDirectory");
    }

    /**
     * Get all the reports available for exporting for the current user.
     *
     * @param Request $request
     * @param Application $app
     * @return \Symfony\Component\HttpFoundation\JsonResponse
     */
    public function getReports(Request $request, Application $app)
    {
        $user = $this->authorize($request, array("acl.nairr-reports"));
        $user_email = $user->getEmailAddress();
        list($_, $report_config) = $this->getConfiguration(
            $request->get('month', null),
            $request->get('year', null)
        );

        $report_list = array();


        foreach ($report_config as $report_id => $report_meta) {

            $is_viewable = $this->isViewable($report_id, $user_email);

            if (!$is_viewable) {
                continue;
            }
            array_push($report_list, array(
                'name' => $report_id,
                'version' => $report_meta['version'] ,
                'title' => $report_meta['title'] ,
                'description' => $report_meta['description'],
                'timestamp' => $report_meta['timestamp'],
            ));

        }

        return $app->json(array(
            'success' => true,
            'report_list' => $report_list,
            'total' => count($report_list)
        ));
    }

    /**
     * Get the report thumbnail image.
     *
     * @param Request $request
     * @param Application $app
     * @param string $report_id
     * @return \Symfony\Component\HttpFoundation\BinaryFileResponse
     * @throws NotFoundHttpException if no report exists with the given ID.
     */
    public function getReport(Request $request, Application $app, $report_id)
    {

        $user = $this->authorize($request, array("acl.nairr-reports"));


        list($base_path, $report_config) = $this->getConfiguration(
            $request->get('month', null),
            $request->get('year', null)
        );

        $user_email = $user->getEmailAddress();
        $is_viewable = $this->isViewable($report_id, $user_email);
        if (!$is_viewable) {
            throw new NotFoundHttpException('You do not have permission to view this report');
        }



        if (isset($report_config[$report_id])) {
            return $app->sendFile(
                $base_path . '/' . $report_config[$report_id]['filename'],
                200,
                [
                    'Content-type' => 'text/html',
                    'Content-Disposition' => sprintf(
                        'attachment; filename="%s"',
                        $report_config[$report_id]['filename']
                    )
                ]
            );
        }

        throw new NotFoundHttpException('Report does not exist');
    }



    public function getReportDirectory(Request $request, Application $app)
    {
        $user = $this->authorize($request, ["acl.nairr-reports"]);
        $base_path = $this->getBasePath();

        $result = [];

        // Get all year directories
        $yearDirs = array_filter(glob($base_path . '/*'), 'is_dir');

        foreach ($yearDirs as $yearPath) {
            $year = basename($yearPath);

            // Get and sort month directories numerically
            $monthDirs = array_filter(glob($yearPath . '/*'), 'is_dir');
            usort($monthDirs, function ($a, $b) {
                return (int) basename($a) <=> (int) basename($b);
            });

            // Add each month as a child node
            $monthChildren = [];
            foreach ($monthDirs as $monthPath) {
                $monthNum = (int) basename($monthPath);
                $dateObj = \DateTime::createFromFormat('!m', $monthNum);
                $monthName = $dateObj->format('F');
                $monthChildren[] = [
                    'text' => $monthName,
                    'leaf' => true
                ];
            }

            // Only add year node if it contains months
            if (!empty($monthChildren)) {
                $result[] = [
                    'text' => $year,
                    'children' => $monthChildren
                ];
            }
        }

        return $app->json($result);
    }

    /**
     * Get the requested data.
     *
     * @param Request $request
     * @param Application $app
     * @param string $report_id
     * @return \Symfony\Component\HttpFoundation\BinaryFileResponse
     * @throws NotFoundHttpException if no report exists with the given ID.
     */
    public function getReportThumbnail(Request $request, Application $app, $report_id)
    {
        $user = $this->authorize($request, array("acl.nairr-reports"));
        list($base_path, $report_config) = $this->getConfiguration(
            $request->get('month', null),
            $request->get('year', null)
        );

        if (isset($report_config[$report_id])) {
            return $app->sendFile($base_path . '/' . $report_config[$report_id]['thumbnail']);
        }

        throw new NotFoundHttpException('Report does not exist');
    }

    /**
     * Get the Custom Report configuration file.
     *
     */

    private function isViewable($report_id, $user_email)
    {
        $viewer_config = $this->getViewerConfig();
        $prefixes = array_keys($viewer_config);
        $pattern = '/^(' . implode('|', array_map('preg_quote', $prefixes)) . ')/';

        if (preg_match($pattern, $report_id, $matches)) {
            $matched_prefix = $matches[1];

            return in_array($user_email, $viewer_config[$matched_prefix]['viewers']);

        }
        return true;

    }

    private function getBasePath()
    {
        $base_path = \xd_utilities\getConfiguration('custom_reports', 'base_path');

        if (!is_dir($base_path)) {
            throw new Exception("Custom reports base path does not exist: $base_path");
        }

        return $base_path;
    }


    private function getConfiguration($month = null, $year = null)
    {
        // Get the base path
        $base_path = $this->getBasePath();

        // Convert month name to number
        $monthNum = null;
        if ($month) {
            $dateObj = \DateTime::createFromFormat('F', ucfirst(strtolower($month)));
            if ($dateObj) {
                $monthNum = (int) $dateObj->format('m'); // 1–12
            }
        }

        // Append year/month to base path if both exist
        if ($monthNum && $year) {
            $base_path .= '/' . $year . '/' . $monthNum;
        }

        // Load the configuration file
        $configFile = $base_path . '/custom_reports.json';


        $report_config_str = file_get_contents($configFile);
        $report_config = json_decode($report_config_str, true);

        return [$base_path, $report_config];
    }

    private function getViewerConfig()
    {
        $base_path = $this->getBasePath();
        $viewer_config_str = file_get_contents($base_path . '/report_reviewer.json');
        $viewer_config = json_decode($viewer_config_str, true);
        if (!$viewer_config) {
            throw new Exception("Failed to parse viewer configuration file.");
        }
        return $viewer_config;

    }

}
