-- Configuración inicial
SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;

--
-- Base de datos: `tfg`
--
CREATE DATABASE IF NOT EXISTS `tfg` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `tfg`;

-- --------------------------------------------------------

--
-- Estructura de tabla para la tabla `usuario`
--
CREATE TABLE `usuario` (
  `idUsuario` int(11) NOT NULL AUTO_INCREMENT,
  `username` varchar(50) NOT NULL,
  `password_hash` varchar(255) NOT NULL,
  `email` varchar(150) NOT NULL,
  PRIMARY KEY (`idUsuario`),
  UNIQUE KEY `username` (`username`),
  UNIQUE KEY `email` (`email`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------

--
-- Estructura de tabla para la tabla `modelo`
--
CREATE TABLE `modelo` (
  `idModelo` int(11) NOT NULL AUTO_INCREMENT,
  `idUsuario` int(11) NOT NULL,
  `nombreModelo` varchar(50) NOT NULL,
  `ficheroConf` text NOT NULL,
  PRIMARY KEY (`idModelo`),
  KEY `idUsuario` (`idUsuario`),
  CONSTRAINT `modelo_ibfk_1` FOREIGN KEY (`idUsuario`) REFERENCES `usuario` (`idUsuario`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------

--
-- Estructura de tabla para la tabla `datasets`
--
CREATE TABLE `datasets` (
  `idDatasets` int(11) NOT NULL AUTO_INCREMENT,
  `idUsuario` int(11) NOT NULL,
  `fichero` longblob NOT NULL,
  `nombreFichero` varchar(50) NOT NULL,
  PRIMARY KEY (`idDatasets`),
  KEY `idUsuario` (`idUsuario`),
  CONSTRAINT `datasets_ibfk_1` FOREIGN KEY (`idUsuario`) REFERENCES `usuario` (`idUsuario`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------

--
-- Estructura de tabla para la tabla `proyectos`
--
CREATE TABLE `proyectos` (
  `idProyecto` int(11) NOT NULL AUTO_INCREMENT,
  `idUsuario` int(11) NOT NULL,
  `idModelo` int(11) NOT NULL,
  `idDatasets` int(11) NOT NULL,
  `nombreProyecto` varchar(50) NOT NULL,
  `fecha` date NOT NULL,
  `estado` varchar(30) NOT NULL,
  `all_circuits` TEXT,
  PRIMARY KEY (`idProyecto`),
  KEY `idUsuario` (`idUsuario`),
  KEY `idModelo` (`idModelo`),
  KEY `idDatasets` (`idDatasets`),
  CONSTRAINT `proyectos_ibfk_1` FOREIGN KEY (`idUsuario`) REFERENCES `usuario` (`idUsuario`) ON DELETE CASCADE,
  CONSTRAINT `proyectos_ibfk_2` FOREIGN KEY (`idModelo`) REFERENCES `modelo` (`idModelo`) ON DELETE CASCADE,
  CONSTRAINT `proyectos_ibfk_3` FOREIGN KEY (`idDatasets`) REFERENCES `datasets` (`idDatasets`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------

--
-- Estructura de tabla para la tabla `resultados`
--
CREATE TABLE `resultados` (
  `idResultado` int(11) NOT NULL AUTO_INCREMENT,
  `idProyecto` int(11) NOT NULL,
  `tipoModelo` varchar(20) NOT NULL,
  `MSE` float NOT NULL,
  `RMSE` float NOT NULL,
  `MAE` float NOT NULL,
  `MAPE` float NOT NULL,
  `R2` float NULL,
  `trainingTime` float NOT NULL,
  `testingTime` float NOT NULL,
  `grafica` mediumblob NULL,
  PRIMARY KEY (`idResultado`),
  KEY `idProyecto` (`idProyecto`),
  CONSTRAINT `resultados_ibfk_1` FOREIGN KEY (`idProyecto`) REFERENCES `proyectos` (`idProyecto`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

COMMIT;